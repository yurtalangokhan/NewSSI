"""Execute the gateway's Lua policy/security code with a request-local transport for APISIX."""

import unittest
from pathlib import Path

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "configs/apisix/plugins/gateway-auth"


class GatewayRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("package.path = ... .. '/?.lua;' .. package.path", str(PLUGIN))
        self.lua.execute(
            "package.preload['apisix.plugins.gateway-auth.broker'] = function() return require('broker') end"
        )

    def test_policy_requires_every_permission_and_denies_unknown_path(self):
        self.lua.execute("""
            package.preload['cjson.safe'] = function() return {} end
            ngx = {re={find=function(path, pattern) return string.find(path, pattern) end}}
            local policy = require('policy')
            local config = {policies={{path='^/protected$', methods={'POST'},
                audience='agent-service', permissions={'agent#read','agent#update'}}}}
            assert(policy.match(config, '/unknown', 'POST') == nil)
            assert(policy.match(config, '/protected', 'GET') == nil)
            local calls = 0
            local ok = policy.authorize(config, '/protected', 'POST', 'token', function(_, _, p)
                calls = calls + 1
                return p == 'agent#read', 403
            end)
            assert(ok == false and calls == 2)
        """)

    def test_token_validation_rejects_wrong_issuer_audience_expiry_and_inactive(self):
        self.lua.execute("""
            package.preload['cjson.safe'] = function() return {} end
            package.preload['resty.http'] = function() return {} end
            local kc = require('keycloak')
            local conf = {issuer_url='https://issuer/realms/test', introspection_client_id='gateway'}
            local good = {active=true, token_type='Bearer', sub='user', iss=conf.issuer_url, aud={'gateway'}, exp=200, nbf=1}
            assert(kc.valid_claims(conf, good, 100))
            good.active=false; assert(not kc.valid_claims(conf, good, 100)); good.active=true
            good.iss='evil'; assert(not kc.valid_claims(conf, good, 100)); good.iss=conf.issuer_url
            good.aud='other'; assert(not kc.valid_claims(conf, good, 100)); good.aud='gateway'
            good.exp=100; assert(not kc.valid_claims(conf, good, 100)); good.exp=200
            good.nbf=101; assert(not kc.valid_claims(conf, good, 100))
            good.nbf=1; good.token_type='Refresh'; assert(not kc.valid_claims(conf, good, 100))
        """)

    def test_session_checks_binding_and_consumes_once(self):
        self.lua.execute("""
            local stored = {}
            package.preload['cjson.safe'] = function() return {
                encode=function(v) return v end, decode=function(v) return v end} end
            package.preload['resty.random'] = function() return {bytes=function() return 'random' end} end
            package.preload['resty.string'] = function() return {to_hex=function(v) return v end} end
            package.preload['resty.sha256'] = function() return {} end
            package.preload['resty.redis'] = function() return {new=function() return {
                set_timeout=function() end, connect=function() return true end,
                set_keepalive=function() end,
                set=function(_, key, value) stored[key]=value; return 'OK' end,
                eval=function(_, _, _, key, binding)
                    local value=stored[key]
                    if value and value.binding == binding then stored[key]=nil; return value end
                end,
            } end} end
            local session = require('session')
            ngx = {null={}}
            local conf = {redis_host='redis',redis_port=6379,redis_database=0}
            assert(session.save(conf,'state',{binding='correct',redirect_uri='https://web/callback'}))
            assert(session.consume(conf,'state','wrong') == nil)
            assert(session.consume(conf,'state','correct').redirect_uri == 'https://web/callback')
            assert(session.consume(conf,'state','correct') == nil)
        """)

    def test_handler_rejects_unknown_routes_and_never_bypasses_bearer_with_internal_key(self):
        self.lua.execute("""
            local decisions = 0
            package.preload['apisix.plugins.gateway-auth.keycloak'] = function() return {
                introspect=function() return {sub='user'} end,
            } end
            package.preload['apisix.plugins.gateway-auth.policy'] = function() return {
                authorize=function() decisions=decisions+1; return false,403 end,
            } end
            package.preload['apisix.plugins.gateway-auth.session'] = function() return {} end
            package.preload['cjson.safe'] = function() return {} end
            ngx = {var={}}
            transport = {request={get_path=function() return '/internal/unknown' end,
                get_method=function() return 'GET' end,
                get_header=function(name)
                    if name=='authorization' then return 'Bearer token' end
                    if name=='x-internal-service-token' then return 'secret' end
                end},
                service={request={clear_header=function() end,set_header=function() end}},
                response={exit=function(status,body) return {status=status,body=body} end}}
            local handler=require('handler').new(transport)
            local result=handler:access({mode='internal',internal_service_token='secret'})
            assert(result.status==403 and decisions==1)
        """)

    def test_verified_user_identity_replaces_spoofed_headers_and_rejects_duplicate_bearer(self):
        self.lua.execute("""
            package.preload['apisix.plugins.gateway-auth.keycloak'] = function() return {
                introspect=function(_,token)
                    assert(token=='valid')
                    return {sub='verified-user',email='alice@example.com',preferred_username='alice',
                        realm_access={roles={'enduser'}},resource_access={app={roles={'reader','enduser'}}}}
                end,
            } end
            package.preload['apisix.plugins.gateway-auth.policy'] = function() return {
                authorize=function(_,path,method)
                    assert(path=='/user-service/api/v1/users/me' and method=='GET')
                    return true
                end,
            } end
            package.preload['apisix.plugins.gateway-auth.session'] = function() return {} end
            package.preload['cjson.safe'] = function() return {} end
            local headers={cookie='access_token=valid', ['x-gateway-user-id']='attacker',
                ['x-gateway-roles']='system-admin', ['x-user-id']='attacker',
                ['x-internal-service-token']='machine', ['x-internal-token']='machine'}
            local api={request={get_path=function() return '/user-service/api/v1/users/me' end,
                get_method=function() return 'GET' end,
                get_header=function(name) return headers[name] end},
                service={request={clear_header=function(name) headers[name]=nil end,
                    set_header=function(name,value) headers[name]=value end}},
                response={exit=function(status) return status end}}
            local handler=require('handler').new(api)
            assert(handler:access({mode='protected',internal_service_token='machine'})==nil)
            assert(headers['x-gateway-user-id']=='verified-user')
            assert(headers['x-gateway-authenticated']=='1' and headers['x-gateway-token']=='machine')
            assert(headers['x-gateway-roles']=='enduser,reader')
            assert(headers['x-gateway-email']=='alice@example.com' and headers['x-gateway-username']=='alice')
            assert(headers.authorization=='Bearer valid')
            assert(headers['x-user-id']==nil and headers['x-internal-service-token']==nil)
            assert(headers['x-internal-token']==nil)
            headers.authorization={'Bearer valid','Bearer second'}
            assert(handler:access({mode='protected',internal_service_token='machine'})==401)
            assert(headers['x-gateway-user-id']==nil)
        """)

    def test_login_preserves_profile_and_rotated_cookie_lifetimes(self):
        self.lua.execute("""
            package.preload['apisix.plugins.gateway-auth.keycloak'] = function() return {
                exchange=function(_, form)
                    assert(form.grant_type=='password' and form.username=='alice')
                    return {access_token='access',refresh_token='refresh',expires_in=120,refresh_expires_in=600}
                end,
                introspect=function() return {sub='user',exp=220,
                    realm_access={roles={'system-admin'}}} end,
                request=function() return {sub='user',email='alice@example.com',
                    preferred_username='alice',email_verified=true,groups={'/team'}} end,
            } end
            package.preload['apisix.plugins.gateway-auth.policy'] = function() return {} end
            package.preload['apisix.plugins.gateway-auth.session'] = function() return {} end
            package.preload['cjson.safe'] = function() return {null={}} end
            ngx = {time=function() return 100 end}
            transport = {request={get_path=function() return '/auth/api/v1/login' end,
                get_method=function() return 'POST' end,get_query=function() return {} end,
                get_header=function() return nil end,
                get_body=function() return {username='alice',password='secret'} end},
                service={request={clear_header=function() end}},
                response={exit=function(status,body,headers) return {status=status,body=body,headers=headers} end}}
            local result=require('handler').new(transport):access({mode='auth',cookie_secure=true})
            assert(result.status==200 and result.body.statusCode==200 and result.body.data.user.id=='user')
            assert(result.body.data.user.role=='system-admin' and result.body.data.user.groups[1]=='/team')
            assert(result.headers['Set-Cookie'][1]:find('Max%-Age=120'))
            assert(result.headers['Set-Cookie'][2]:find('Max%-Age=600'))
            assert(result.headers['Set-Cookie'][1]:find('Secure'))
        """)

    def test_auth_rejects_cross_origin_login(self):
        self.lua.execute("""
            package.preload['apisix.plugins.gateway-auth.keycloak'] = function() return {} end
            package.preload['apisix.plugins.gateway-auth.policy'] = function() return {} end
            package.preload['apisix.plugins.gateway-auth.session'] = function() return {} end
            package.preload['cjson.safe'] = function() return {} end
            transport={request={get_path=function() return '/auth/api/v1/login' end,
                get_method=function() return 'POST' end,get_header=function() return 'https://evil.example' end},
                service={request={clear_header=function() end}},
                response={exit=function(status) return status end}}
            assert(require('handler').new(transport):access({mode='auth',
                allowed_redirect_uris={'https://app.example/auth/oidc/callback'}})==403)
        """)

    def test_cookie_authenticated_mutation_rejects_untrusted_origin(self):
        self.lua.execute("""
            package.preload['apisix.plugins.gateway-auth.keycloak'] = function() return {} end
            package.preload['apisix.plugins.gateway-auth.policy'] = function() return {} end
            package.preload['apisix.plugins.gateway-auth.session'] = function() return {} end
            package.preload['cjson.safe'] = function() return {} end
            transport={request={get_path=function() return '/user-service/api/v1/users' end,
                get_method=function() return 'POST' end,get_header=function(name)
                    if name=='origin' then return 'https://untrusted.example' end
                    if name=='cookie' then return 'access_token=token' end
                    if name=='authorization' then return 'Bearer token' end
                end},service={request={clear_header=function() end}},
                response={exit=function(status) return status end}}
            assert(require('handler').new(transport):access({mode='protected',
                allowed_redirect_uris={'https://app.example/auth/oidc/callback'}})==403)
        """)

    def test_legacy_tools_machine_headers_preserve_authenticated_delegation(self):
        self.lua.execute("""
            package.preload['apisix.plugins.gateway-auth.keycloak'] = function() return {} end
            package.preload['apisix.plugins.gateway-auth.policy'] = function() return {} end
            package.preload['apisix.plugins.gateway-auth.session'] = function() return {} end
            package.preload['cjson.safe'] = function() return {} end
            local upstream = {}
            local headers = {authorization='Bearer machine-secret', ['x-internal-token']='machine-secret',
                ['x-user-id']='delegated-user'}
            transport={request={get_path=function() return '/internal/tools-service/mcp' end,
                get_method=function() return 'POST' end,get_header=function(name) return headers[name] end},
                service={request={clear_header=function(name) upstream[name]=nil end,
                    set_header=function(name,value) upstream[name]=value end}},
                response={exit=function(status) return status end}}
            local result=require('handler').new(transport):access({mode='internal',internal_service_token='machine-secret'})
            assert(result==nil and upstream['x-user-id']=='delegated-user')
            assert(upstream['x-internal-token']=='machine-secret')
            headers['x-internal-service-token']='conflict'
            assert(require('handler').new(transport):access({mode='internal',internal_service_token='machine-secret'})==401)
        """)

    def test_keycloak_outage_and_partial_uma_responses_fail_closed(self):
        self.lua.execute("""
            local response
            package.preload['cjson.safe'] = function() return {decode=function(value) return value end} end
            package.preload['resty.http'] = function() return {new=function() return {
                set_timeout=function() end,request_uri=function() return response end,
            } end} end
            ngx={encode_args=function(value) return value end}
            local kc=require('keycloak')
            local conf={keycloak_base_url='https://issuer/realms/test'}
            local allowed,status=kc.decide(conf,'token','agent-service','agent#read')
            assert(not allowed and status==503)
            response={status=200,body={result=false}}
            assert(kc.decide(conf,'token','agent-service','agent#read')==false)
            response={status=200,body={result=true}}
            assert(kc.decide(conf,'token','agent-service','agent#read')==true)
            response={status=204,body=''}
            local data,code=kc.request(conf,'logout',{})
            assert(data and code==204)
        """)

    # ------------------------------------------------------------------
    # External (SP Keycloak SSO) broker password login
    # ------------------------------------------------------------------
    BROKER_ENV = """
        ngx = {
            encode_args=function(args)
                local keys, parts = {}, {}
                for k in pairs(args) do keys[#keys+1]=k end
                table.sort(keys)
                for _, k in ipairs(keys) do parts[#parts+1]=k..'='..tostring(args[k]) end
                return table.concat(parts, '&')
            end,
            decode_args=function(query)
                local args = {}
                for k, v in query:gmatch('([^&=]+)=([^&]*)') do args[k]=v end
                return args
            end,
        }
        broker = require('broker')
        LOGIN_PAGE = [[<html><form id="kc-form-login" action="/realms/corp/login-actions/authenticate?session_code=a&amp;tab_id=b" method="post">
            <input tabindex="1" id="username" name="username" value="" type="text"/>
            <input id="password" name="password" type="password"/>
            <input type="hidden" id="id-hidden-input" name="credentialId"/></form></html>]]
        function fake_idp(opts)
            local calls = {}
            local client = {set_timeout=function() end}
            function client:request_uri(url, params)
                calls[#calls+1] = {url=url, method=params.method, body=params.body, cookie=params.headers.Cookie}
                if url:find('^https://sp%.example/realms/app/protocol/openid%-connect/auth') then
                    return {status=302, headers={Location='https://idp.example/realms/corp/auth?x=1',
                        ['Set-Cookie']={'AUTH_SESSION_ID=sp1; Path=/realms/app/; HttpOnly'}}}
                end
                if url == 'https://idp.example/realms/corp/auth?x=1' then
                    return {status=200, body=opts.page or LOGIN_PAGE, headers={
                        ['Set-Cookie']={'AUTH_SESSION_ID=idp1; Path=/realms/corp/', 'KC_RESTART=r; Path=/realms/corp/'}}}
                end
                if params.method == 'POST' then
                    if params.body:find('password=' .. opts.password, 1, true) then
                        return {status=302, headers={Location='https://sp.example/realms/app/broker/corp/endpoint?code=idp'}}
                    end
                    return {status=200, body=LOGIN_PAGE, headers={}}
                end
                if url:find('/broker/corp/endpoint', 1, true) then
                    assert(params.headers.Cookie == 'AUTH_SESSION_ID=sp1', 'SP cookie must be replayed only to SP')
                    return {status=302, headers={Location='http://localhost:3000/auth/oidc/callback?state=' ..
                        (opts.state or 'st') .. '&code=the-code'}}
                end
                error('unexpected request ' .. url)
            end
            return client, calls
        end
        conf = {broker_url_rewrites={}}
        AUTH = 'https://sp.example/realms/app/protocol/openid-connect/auth?kc_idp_hint=corp'
        CALLBACK = 'http://localhost:3000/auth/oidc/callback'
    """

    def test_broker_helpers_parse_forms_urls_and_path_scoped_cookies(self):
        self.lua.execute(
            self.BROKER_ENV
            + """
            assert(broker.unescape('a&amp;b&#39;c&#x2F;d&nbsp;') == "a&b'c/d&nbsp;")
            assert(broker.join('https://h.example/a/b?q=1', '/x') == 'https://h.example/x')
            assert(broker.join('https://h.example/a/b?q=1', 'c') == 'https://h.example/a/c')
            assert(broker.join('https://h.example', '?y=2') == 'https://h.example?y=2')
            assert(broker.join('https://h.example/a', 'https://o.example/z') == 'https://o.example/z')
            assert(broker.rewrite({['https://pub.example']='http://idp:8080'}, 'https://pub.example/realms/x')
                == 'http://idp:8080/realms/x')
            local action, inputs = broker.login_form(LOGIN_PAGE, 'https://idp.example/realms/corp/auth?x=1')
            assert(action == 'https://idp.example/realms/corp/login-actions/authenticate?session_code=a&tab_id=b', action)
            assert(inputs.username == '' and inputs.password == '' and inputs.credentialId == '')
            assert(broker.login_form('<html>no form</html>', 'https://h.example/') == nil)
            local jar = {}
            broker.store(jar, 'https://kc.example/realms/app/x', {'AUTH_SESSION_ID=app; Path=/realms/app/'})
            broker.store(jar, 'https://kc.example/realms/corp/x', {'AUTH_SESSION_ID=corp; Path=/realms/corp/'})
            assert(broker.cookie_header(jar, 'https://kc.example/realms/app/y') == 'AUTH_SESSION_ID=app')
            assert(broker.cookie_header(jar, 'https://kc.example/realms/corp/y') == 'AUTH_SESSION_ID=corp')
            assert(broker.cookie_header(jar, 'https://other.example/realms/app/y') == nil)
            broker.store(jar, 'https://kc.example/realms/app/x', 'AUTH_SESSION_ID=; Path=/realms/app/; Max-Age=0')
            assert(broker.cookie_header(jar, 'https://kc.example/realms/app/y') == nil)
        """
        )

    def test_broker_password_login_returns_code_and_scopes_cookies(self):
        self.lua.execute(
            self.BROKER_ENV
            + """
            local client, calls = fake_idp({password='right'})
            local code, status, reason = broker.password_login(conf, AUTH, CALLBACK, 'st', 'yusuf', 'right', client)
            assert(code == 'the-code', tostring(status) .. ' ' .. tostring(reason))
            local post
            for _, call in ipairs(calls) do if call.method == 'POST' then post = call end end
            assert(post.url:find('^https://idp%.example/realms/corp/login%-actions/authenticate'))
            assert(post.cookie == 'AUTH_SESSION_ID=idp1; KC_RESTART=r' or post.cookie == 'KC_RESTART=r; AUTH_SESSION_ID=idp1')
            for _, call in ipairs(calls) do assert(not call.url:find('localhost'), 'callback must not be fetched') end
        """
        )

    def test_broker_password_login_reports_rejected_credentials_and_bad_state(self):
        self.lua.execute(
            self.BROKER_ENV
            + """
            local client = fake_idp({password='right'})
            local code, status, reason = broker.password_login(conf, AUTH, CALLBACK, 'st', 'yusuf', 'wrong', client)
            assert(code == nil and status == 401 and reason == 'credentials_rejected')
            client = fake_idp({password='right', state='forged'})
            code, status, reason = broker.password_login(conf, AUTH, CALLBACK, 'st', 'yusuf', 'right', client)
            assert(code == nil and status == 401 and reason == 'state_mismatch')
        """
        )

    def test_broker_never_posts_credentials_cross_origin(self):
        self.lua.execute(
            self.BROKER_ENV
            + """
            local page = '<form action="https://evil.example/steal"><input name="username"/></form>'
            local client, calls = fake_idp({password='right', page=page})
            local code, status, reason = broker.password_login(conf, AUTH, CALLBACK, 'st', 'yusuf', 'right', client)
            assert(code == nil and status == 503 and reason == 'login_form_cross_origin')
            for _, call in ipairs(calls) do assert(call.method ~= 'POST') end
        """
        )

    def test_external_broker_rejects_internal_realm_password_form(self):
        self.lua.execute(
            self.BROKER_ENV
            + """
            for _, rewrites in ipairs({{}, {['https://sp.example']='http://keycloak:8080'}}) do
                local client = {set_timeout=function() end}
                function client:request_uri(url, params)
                    assert(params.method == 'GET', 'external credentials must never be posted to SP')
                    return {status=200, headers={}, body=[[
                        <form action="/realms/app/login-actions/authenticate">
                        <input name="username"/><input name="password"/></form>]]}
                end
                local code, status, reason = broker.password_login(
                    {broker_url_rewrites=rewrites}, AUTH, CALLBACK, 'st', 'user', 'pass', client)
                assert(code == nil and status == 503 and reason == 'external_idp_not_reached')
            end
        """
        )

    def test_external_broker_accepts_another_realm_on_the_same_host(self):
        self.lua.execute(
            self.BROKER_ENV
            + """
            local posted = false
            local client = {set_timeout=function() end}
            function client:request_uri(url, params)
                if url == AUTH then
                    return {status=302, headers={Location='https://sp.example/realms/app-external/auth'}}
                end
                if params.method == 'POST' then
                    assert(url == 'https://sp.example/realms/app-external/login-actions/authenticate')
                    posted = true
                    return {status=302, headers={Location=CALLBACK .. '?state=st&code=external-code'}}
                end
                return {status=200, headers={}, body=[[
                    <form action="/realms/app-external/login-actions/authenticate">
                    <input name="username"/><input name="password"/></form>]]}
            end
            local code = broker.password_login(conf, AUTH, CALLBACK, 'st', 'user', 'pass', client)
            assert(posted and code == 'external-code')
        """
        )

    def test_external_login_with_credentials_uses_broker_and_maps_bad_password(self):
        self.lua.execute("""
            package.preload['apisix.plugins.gateway-auth.keycloak'] = function() return {
                exchange=function() error('exchange must not run after rejected credentials') end} end
            package.preload['apisix.plugins.gateway-auth.policy'] = function() return {} end
            package.preload['apisix.plugins.gateway-auth.session'] = function() return {
                random=function() return 'rnd' end, challenge=function() return 'chal' end} end
            package.preload['apisix.plugins.gateway-auth.broker'] = function() return {
                password_login=function(conf, url, redirect_uri, state, username, password)
                    assert(url:find('kc_idp_hint=corp', 1, true) and redirect_uri == 'https://app.example/auth/oidc/callback')
                    assert(username == 'yusuf' and password == 'bad')
                    return nil, 401, 'credentials_rejected'
                end} end
            package.preload['cjson.safe'] = function() return {} end
            ngx = {encode_args=function(args) return 'kc_idp_hint=' .. args.kc_idp_hint end}
            transport = {log={warn=function() end},
                request={get_path=function() return '/auth/api/v1/external/login' end,
                get_method=function() return 'POST' end,
                get_query=function() return {redirect_uri='https://app.example/auth/oidc/callback'} end,
                get_header=function() return nil end,
                get_body=function() return {username='yusuf',password='bad'} end},
                service={request={clear_header=function() end}},
                response={exit=function(status,body) return {status=status,body=body} end}}
            local result=require('handler').new(transport):access({mode='auth', external_idp_alias='corp',
                issuer_url='https://sp.example/realms/app', login_client_id='web',
                allowed_redirect_uris={'https://app.example/auth/oidc/callback'}})
            assert(result.status==401 and result.body.statusCode==401)
            assert(result.body.error.code=='auth.invalid_credentials' and result.body.data==nil)
        """)

    def test_local_auth_responses_use_the_response_model_envelope(self):
        self.lua.execute("""
            package.preload['apisix.plugins.gateway-auth.keycloak'] = function() return {} end
            package.preload['apisix.plugins.gateway-auth.policy'] = function() return {} end
            package.preload['apisix.plugins.gateway-auth.session'] = function() return {} end
            package.preload['cjson.safe'] = function() return {null={}} end
            local function run(method, path, conf)
                transport = {request={get_path=function() return path end,
                    get_method=function() return method end,get_query=function() return {} end,
                    get_header=function() return nil end,get_body=function() return nil end},
                    service={request={clear_header=function() end}},
                    response={exit=function(status,body,headers) return {status=status,body=body,headers=headers} end}}
                return require('handler').new(transport):access(conf)
            end
            local kind = run('GET', '/user-service/api/v1/auth/type', {mode='auth', external_idp_alias='corp'})
            local null = require('cjson.safe').null
            assert(kind.status==200 and kind.body.statusCode==200 and kind.body.error==null)
            assert(kind.body.data.externalKeycloak==true and kind.body.data.externalKeycloakAlias=='corp')
            assert(kind.body.data.authType=='oidc' and kind.headers['Cache-Control']=='no-store')
            local plain = run('GET', '/auth/api/v1/type', {mode='auth', external_idp_alias=''})
            assert(plain.body.data.externalKeycloak==false)
            local unknown = run('GET', '/auth/api/v1/nope', {mode='auth'})
            assert(unknown.status==404 and unknown.body.statusCode==404 and unknown.body.data==null)
            assert(unknown.body.error.code=='request.not_found' and unknown.body.message==unknown.body.error.message)
            local denied = run('GET', '/anything', {mode='protected', internal_service_token='x'})
            assert(denied.status==401 and denied.body.error.code=='auth.unauthorized')
        """)

    def test_basic_login_maps_rejected_password_to_bad_credentials(self):
        self.lua.execute("""
            package.preload['apisix.plugins.gateway-auth.keycloak'] = function() return {
                exchange=function() return nil, 401 end} end
            package.preload['apisix.plugins.gateway-auth.policy'] = function() return {} end
            package.preload['apisix.plugins.gateway-auth.session'] = function() return {} end
            package.preload['cjson.safe'] = function() return {} end
            transport = {request={get_path=function() return '/auth/api/v1/login' end,
                get_method=function() return 'POST' end,get_query=function() return {} end,
                get_header=function() return nil end,
                get_body=function() return {username='alice',password='nope'} end},
                service={request={clear_header=function() end}},
                response={exit=function(status,body) return {status=status,body=body} end}}
            local result=require('handler').new(transport):access({mode='auth'})
            assert(result.status==401 and result.body.statusCode==401)
            assert(result.body.error.code=='auth.invalid_credentials' and result.body.data==nil)
        """)


class ApisixAdapterTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("plugin_file = ...", str(PLUGIN.parent / "gateway-auth.lua"))
        self.lua.execute("""
            headers, response_headers, request_body, content_type = {}, {}, '', 'application/json'
            ctx = {var={uri='/auth/api/v1/login'}}
            ngx = {header=response_headers, decode_args=function(body)
                assert(body=='username=alice&password=secret')
                return {username='alice', password='secret'}
            end}
            package.preload['apisix.core'] = function() return {
                request={headers=function() return headers end,
                    set_header=function(_, name, value) headers[name]=value end,
                    get_uri_args=function() return {redirect_uri='https://app/callback'} end,
                    get_method=function() return 'POST' end,
                    get_body=function() return request_body end},
                schema={check=function(schema, conf) captured_schema=schema; return true end},
                log={warn=function() end},
            } end
            package.preload['cjson.safe'] = function() return {decode=function(raw)
                if raw=='valid' then return {username='alice',password='secret'} end
                return nil
            end} end
            package.preload['apisix.plugins.gateway-auth.handler'] = function() return {
                new=function(api) transport=api; return {access=function(_, conf)
                    return callback(api, conf)
                end} end,
            } end
        """)

    def test_native_phase_preserves_path_duplicate_headers_and_response_cookies(self):
        self.lua.execute("""
            callback=function(api)
                assert(api.request.get_path()=='/auth/api/v1/login')
                assert(api.request.get_method()=='POST')
                assert(api.request.get_query().redirect_uri=='https://app/callback')
                assert(type(api.request.get_header('authorization'))=='table')
                api.service.request.clear_header('x-gateway-user-id')
                api.service.request.set_header('x-gateway-user-id', 'verified')
                return api.response.exit(200, {ok=true}, {
                    ['Set-Cookie']={'access_token=a', 'refresh_token=b'}, ['Cache-Control']='no-store'})
            end
            headers.authorization={'Bearer one','Bearer two'}
            headers['x-gateway-user-id']='forged'
            local plugin=dofile(plugin_file)
            assert(plugin.priority > 1008)
            local status, body=plugin.rewrite({}, ctx)
            assert(status==200 and body.ok)
            assert(headers['x-gateway-user-id']=='verified')
            assert(#response_headers['Set-Cookie']==2)
            assert(response_headers['Cache-Control']=='no-store')
            assert(plugin.check_schema({}))
            assert(captured_schema.properties.mode.enum[3]=='internal')
            assert(captured_schema.properties.policy_file.default=='/usr/local/apisix/conf/gateway-policies.json')
        """)

    def test_json_form_and_malformed_bodies(self):
        self.lua.execute("""
            callback=function(api) return 200, api.request.get_body() end
            local plugin=dofile(plugin_file)
            headers['content-type']='application/json; charset=utf-8'; request_body='valid'
            local status, body=plugin.rewrite({},ctx)
            assert(status==200 and body.username=='alice')
            headers['content-type']='application/x-www-form-urlencoded; charset=UTF-8'
            request_body='username=alice&password=secret'
            status, body=plugin.rewrite({},ctx)
            assert(body.password=='secret')
            headers['content-type']='application/json'; request_body='invalid'
            status, body=plugin.rewrite({},ctx)
            assert(body==nil)
            headers['content-type']={'application/json','text/plain'}
            status, body=plugin.rewrite({},ctx)
            assert(body==nil)
            headers['content-type']='text/plain'; request_body='valid'
            status, body=plugin.rewrite({},ctx)
            assert(body==nil)
        """)


if __name__ == "__main__":
    unittest.main()
