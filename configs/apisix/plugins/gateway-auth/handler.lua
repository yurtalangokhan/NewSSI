local kc = require "apisix.plugins.gateway-auth.keycloak"
local policy = require "apisix.plugins.gateway-auth.policy"
local session = require "apisix.plugins.gateway-auth.session"
local broker = require "apisix.plugins.gateway-auth.broker"
local json = require "cjson.safe"
local M = {}
function M.new(api)
local Handler = {PRIORITY = 1005, VERSION = "1.0.0"}

-- Every response the gateway answers itself uses the platform ResponseModel
-- envelope, so clients parse it exactly like a user-service response. Error
-- codes come from the shared error contract.
local function respond(status, data, headers)
  return api.response.exit(status,
    {statusCode = status, message = json.null, data = data, error = json.null}, headers)
end

local function respond_error(status, code, message, headers)
  return api.response.exit(status, {statusCode = status, message = message, data = json.null,
    error = {code = code, message = message}}, headers)
end

local FAILURES = {
  [401] = {"auth.unauthorized", "Authentication required"},
  [403] = {"auth.forbidden", "Access denied"},
  [502] = {"dependency.invalid_response", "Identity provider returned an invalid response"},
  [504] = {"dependency.timeout", "Identity provider timed out"},
}
local UNAVAILABLE = {"dependency.unavailable", "Identity provider unavailable"}

local function fail(status, step)
  status = status or 503
  -- Name the rejecting step in the gateway log; clients only see the status.
  if step and api.log then api.log.warn("gateway-auth rejected at ", step, ": status ", status) end
  local failure = FAILURES[status] or UNAVAILABLE
  return respond_error(status, failure[1], failure[2], {["Cache-Control"] = "no-store"})
end

local function cookie(name)
  local header = api.request.get_header("cookie") or ""
  if type(header) ~= "string" then return nil end
  for key, value in header:gmatch("([^;= ]+)=([^;]*)") do
    if key == name then return value end
  end
end

local function bearer()
  local authorization = api.request.get_header("authorization")
  if authorization then
    if type(authorization) ~= "string" then return nil, true end
    local value = authorization:match("^[Bb][Ee][Aa][Rr][Ee][Rr] ([^ ]+)$")
    return value, value == nil
  end
  return cookie("access_token") or cookie("fastapiusersauth")
end

local function make_cookie(conf, name, value, lifetime)
  return name .. "=" .. value .. "; Path=/; HttpOnly; SameSite=Lax; Max-Age=" ..
    tostring(lifetime) .. (conf.cookie_secure and "; Secure" or "")
end

local function lifetime(value, fallback)
  local number = tonumber(value)
  if not number or number <= 0 then return fallback end
  return math.floor(number)
end

local function clear_cookies(conf)
  local result = {}
  for _, name in ipairs({"access_token", "refresh_token", "id_token", "fastapiusersauth", "gateway_oidc_binding"}) do
    result[#result + 1] = make_cookie(conf, name, "", 0)
  end
  return result
end

local function allowed_redirect(conf, uri)
  if type(uri) ~= "string" then return false end
  for _, allowed in ipairs(conf.allowed_redirect_uris or {}) do
    if uri == allowed then return true end
  end
  return false
end

local function authorize(conf, query, idp)
  if not allowed_redirect(conf, query.redirect_uri) then return fail(403) end
  local state, binding, verifier, nonce = session.random(), session.random(), session.random(), session.random()
  if not state or not binding or not verifier or not nonce then return fail(503) end
  if not session.save(conf, state, {binding = binding, verifier = verifier, nonce = nonce,
      redirect_uri = query.redirect_uri}) then return fail(503) end
  local parameters = {client_id = conf.login_client_id, response_type = "code",
    scope = "openid profile email", redirect_uri = query.redirect_uri,
    state = state, nonce = nonce, code_challenge = session.challenge(verifier), code_challenge_method = "S256"}
  if idp and idp ~= "" then parameters.kc_idp_hint = idp end
  if query.prompt == "login" or query.prompt == "none" or query.prompt == "select_account" then
    parameters.prompt = query.prompt
  end
  local url = conf.issuer_url .. "/protocol/openid-connect/auth?" .. ngx.encode_args(parameters)
  return respond(200, {authorization_url = url, authorize_url = url}, {
    ["Set-Cookie"] = {make_cookie(conf, "gateway_oidc_binding", binding, 300)}, ["Cache-Control"] = "no-store",
  })
end

local function primary_role(claims)
  local roles = claims.realm_access and claims.realm_access.roles or {}
  for _, priority in ipairs({"system-admin", "enterprise-admin"}) do
    for _, role in ipairs(roles) do if role == priority then return priority end end
  end
  return claims.primary_role or "enduser"
end

-- Roles carried to the upstream service. Backends use these for coarse checks
-- only; fine-grained permissions still resolve through user-service.
local function gateway_roles(claims)
  local seen, ordered = {}, {}
  local function add(list)
    if type(list) ~= "table" then return end
    for _, role in ipairs(list) do
      local value = tostring(role)
      if value ~= "" and not seen[value] then
        seen[value] = true
        ordered[#ordered + 1] = value
      end
    end
  end
  if type(claims.realm_access) == "table" then add(claims.realm_access.roles) end
  if type(claims.resource_access) == "table" then
    for _, client in pairs(claims.resource_access) do
      if type(client) == "table" then add(client.roles) end
    end
  end
  return table.concat(ordered, ",")
end

-- The single place identity crosses from Gateway to a backend service.
-- x-gateway-token proves the request traversed Gateway; it never grants machine
-- identity. Inbound copies of every header set here are stripped in access().
local function set_gateway_identity(conf, claims)
  -- Backends key identity off the subject, so a token without one must not
  -- reach an upstream service.
  if type(claims.sub) ~= "string" or claims.sub == "" then return false end
  api.service.request.set_header("x-gateway-token", conf.internal_service_token)
  api.service.request.set_header("x-gateway-authenticated", "1")
  api.service.request.set_header("x-gateway-user-id", claims.sub)
  local email = claims.email or claims.preferred_username or ""
  if email ~= "" then api.service.request.set_header("x-gateway-email", email) end
  local username = claims.preferred_username or ""
  if username ~= "" then api.service.request.set_header("x-gateway-username", username) end
  local roles = gateway_roles(claims)
  if roles ~= "" then api.service.request.set_header("x-gateway-roles", roles) end
  return true
end

local function login_response(conf, tokens, expected_nonce)
  if type(tokens.access_token) ~= "string" or tokens.access_token == "" then return fail(503, "token_response_without_access_token") end
  local claims, status = kc.introspect(conf, tokens.access_token)
  if not claims then return fail(status, "introspection") end
  if expected_nonce then
    -- Token response came directly from the configured Keycloak endpoint over verified transport.
    -- Bind its ID token to our single-use authorization transaction as well as its subject.
    local encoded = type(tokens.id_token) == "string" and tokens.id_token:match("^[^.]+%.([^.]+)%.")
    local raw = encoded and ngx.decode_base64(encoded:gsub("-", "+"):gsub("_", "/"))
    local id_claims = raw and json.decode(raw)
    if type(id_claims) ~= "table" or id_claims.nonce ~= expected_nonce or
        id_claims.sub ~= claims.sub or id_claims.iss ~= conf.issuer_url then return fail(401, "id_token_binding") end
  end
  local profile, profile_status = kc.request(conf, "userinfo", nil, tokens.access_token)
  if not profile then return fail(profile_status, "userinfo") end
  if profile.sub ~= claims.sub then return fail(401, "userinfo_subject_mismatch") end
  local expires = lifetime(tokens.expires_in, math.max(1, claims.exp - ngx.time()))
  local refresh_expires = lifetime(tokens.refresh_expires_in, 30 * 86400)
  local cookies = {make_cookie(conf, "access_token", tokens.access_token, expires)}
  if type(tokens.refresh_token) == "string" and tokens.refresh_token ~= "" then
    cookies[#cookies + 1] = make_cookie(conf, "refresh_token", tokens.refresh_token, refresh_expires)
  end
  local payload = {access_token = tokens.access_token, refresh_token = tokens.refresh_token or "",
    token_type = tokens.token_type or "Bearer", expires_in = expires,
    refresh_expires_in = tokens.refresh_expires_in or json.null,
    user = {id = claims.sub, email = profile.email or "", username = profile.preferred_username or json.null,
      first_name = profile.given_name or json.null, last_name = profile.family_name or json.null,
      role = primary_role(claims), is_active = true, is_verified = profile.email_verified == true,
      groups = profile.groups or claims.groups or json.empty_array or {}}}
  if type(tokens.id_token) == "string" then
    payload.id_token = tokens.id_token
    local candidate = make_cookie(conf, "id_token", tokens.id_token, refresh_expires)
    local size = #candidate
    for _, item in ipairs(cookies) do size = size + #item end
    if #tokens.id_token <= 3800 and size <= 3900 then cookies[#cookies + 1] = candidate end
  end
  if expected_nonce then cookies[#cookies + 1] = make_cookie(conf, "gateway_oidc_binding", "", 0) end
  return respond(200, payload, {["Set-Cookie"] = cookies, ["Cache-Control"] = "no-store"})
end

local function bad_credentials()
  return respond_error(401, "auth.invalid_credentials", "Invalid username or password",
    {["Cache-Control"] = "no-store"})
end

-- Username/password login on the external IdP, brokered by the SP realm and
-- performed by the gateway itself (no browser round trip to the IdP page).
local function external_password_login(conf, query, username, password)
  if not allowed_redirect(conf, query.redirect_uri) then return fail(403) end
  local state, verifier, nonce = session.random(), session.random(), session.random()
  if not state or not verifier or not nonce then return fail(503) end
  local url = conf.issuer_url .. "/protocol/openid-connect/auth?" .. ngx.encode_args({
    client_id = conf.login_client_id, response_type = "code", scope = "openid profile email",
    redirect_uri = query.redirect_uri, state = state, nonce = nonce,
    code_challenge = session.challenge(verifier), code_challenge_method = "S256",
    kc_idp_hint = conf.external_idp_alias,
  })
  local code, status, reason = broker.password_login(conf, url, query.redirect_uri, state, username, password)
  if not code then
    api.log.warn("external broker login failed: ", reason)
    if status == 401 then return bad_credentials() end
    if status == 409 then
      return respond_error(409, "auth.external_login_requires_browser",
        "The identity provider requires an interactive browser login", {["Cache-Control"] = "no-store"})
    end
    return fail(status)
  end
  local tokens, exchange_status = kc.exchange(conf, {grant_type = "authorization_code", code = code,
    redirect_uri = query.redirect_uri, code_verifier = verifier})
  if not tokens then return fail(exchange_status, "external_code_exchange") end
  return login_response(conf, tokens, nonce)
end

local function trusted_origin(conf, method)
  if method == "GET" or method == "HEAD" or method == "OPTIONS" then return true end
  local origin = api.request.get_header("origin")
  if not origin then return true end
  for _, uri in ipairs(conf.allowed_redirect_uris or {}) do
    if uri:match("^(https?://[^/]+)") == origin then return true end
  end
  return false
end

local function auth(conf, path, method)
  if not trusted_origin(conf, method) then return fail(403) end
  local suffix = path:match("^/auth/api/v1(/.*)$") or path:match("^/user%-service/api/v1/auth(/.*)$")
  local query = api.request.get_query()
  if method == "GET" and suffix == "/type" then
    local external = conf.external_idp_alias ~= nil and conf.external_idp_alias ~= ""
    return respond(200, {authType = "oidc", keycloakEnabled = true, oauthEnabled = true,
      externalKeycloak = external, external_keycloak = external,
      externalKeycloakAlias = external and conf.external_idp_alias or json.null}, {["Cache-Control"] = "no-store"})
  end
  if method == "GET" and suffix == "/oidc/authorize" then
    -- Only broker to the external IdP when the caller asks for it; the plain
    -- authorize flow is the SP (local realm) login, matching user-service.
    return authorize(conf, query, query.kc_idp_hint)
  end
  if method == "POST" and suffix == "/external/login" then
    if not conf.external_idp_alias or conf.external_idp_alias == "" then return fail(403) end
    local body = api.request.get_body()
    if type(body) == "table" and type(body.username) == "string" and body.username ~= "" and
        type(body.password) == "string" and body.password ~= "" then
      return external_password_login(conf, query, body.username, body.password)
    end
    return authorize(conf, query, conf.external_idp_alias)
  end
  if method == "POST" and suffix == "/logout" then
    local refresh = cookie("refresh_token")
    local status = 200
    if refresh then
      local form = {client_id = conf.login_client_id, refresh_token = refresh}
      if conf.login_client_secret and conf.login_client_secret ~= "" then form.client_secret = conf.login_client_secret end
      -- Keycloak returns 204 without a body on successful revocation.
      local _, result = kc.request(conf, "logout", form)
      if result == 503 then status = 503 end
    end
    local headers = {["Set-Cookie"] = clear_cookies(conf), ["Cache-Control"] = "no-store"}
    if status == 200 then return respond(200, {message = "Logged out successfully"}, headers) end
    return respond_error(status, UNAVAILABLE[1],
      "Local session cleared; identity provider unavailable", headers)
  end
  local form, nonce
  if method == "POST" and suffix == "/login" then
    local body = api.request.get_body()
    if type(body) ~= "table" or type(body.username) ~= "string" or type(body.password) ~= "string" then
      return respond_error(400, "request.invalid", "Username and password are required")
    end
    form = {grant_type = "password", username = body.username, password = body.password, scope = "openid profile email"}
  elseif method == "POST" and suffix == "/refresh" then
    local refresh = cookie("refresh_token")
    if not refresh then return fail(401) end
    form = {grant_type = "refresh_token", refresh_token = refresh}
  elseif method == "GET" and suffix == "/oidc/callback" then
    local transaction, status = session.consume(conf, query.state, cookie("gateway_oidc_binding"))
    if not transaction then return fail(status or 401) end
    if query.redirect_uri ~= transaction.redirect_uri or type(query.code) ~= "string" then return fail(401) end
    form = {grant_type = "authorization_code", code = query.code,
      redirect_uri = transaction.redirect_uri, code_verifier = transaction.verifier}
    nonce = transaction.nonce
  else
    return respond_error(404, "request.not_found", "Unknown authentication endpoint")
  end
  local tokens, status = kc.exchange(conf, form)
  if not tokens then
    if status == 401 and suffix == "/login" then return bad_credentials() end
    return fail(status)
  end
  return login_response(conf, tokens, nonce)
end

function Handler:access(conf)
  local delegated_user = api.request.get_header("x-user-id")
  for _, name in ipairs({"x-gateway-token", "x-gateway-user-id", "x-gateway-authenticated",
      "x-gateway-roles", "x-gateway-email", "x-gateway-username",
      "x-user-id", "x-consumer-id", "x-consumer-username", "x-credential-identifier"}) do
    api.service.request.clear_header(name)
  end
  local path, method = api.request.get_path(), api.request.get_method()
  if conf.mode == "auth" then return auth(conf, path, method) end
  local token, invalid = bearer()
  if invalid then return fail(401) end
  local internal_token = api.request.get_header("x-internal-service-token")
  local internal_alias = api.request.get_header("x-internal-token")
  if conf.mode == "internal" then
    if internal_token and internal_alias and internal_token ~= internal_alias then return fail(401) end
    local credential = internal_token or internal_alias
    if not token or token == conf.internal_service_token then
      if (credential and credential ~= conf.internal_service_token) or
          (not credential and token ~= conf.internal_service_token) then return fail(401) end
      -- Existing machine adapters use a bearer shared secret and the tools header alias.
      -- Delegation is trusted only after authenticating that machine credential.
      api.service.request.set_header("x-gateway-token", conf.internal_service_token)
      api.service.request.set_header("x-internal-service-token", conf.internal_service_token)
      api.service.request.set_header("x-internal-token", conf.internal_service_token)
      if type(delegated_user) == "string" and delegated_user ~= "" then
        api.service.request.set_header("x-user-id", delegated_user)
      end
      return
    end
  end
  -- A user credential always takes the user authorization path, including internal routes.
  if not token then return fail(401) end
  -- The web proxy may synthesize Authorization from its access-token cookie.
  if not trusted_origin(conf, method) then
    return fail(403)
  end
  local claims, status = kc.introspect(conf, token)
  if not claims then return fail(status) end
  local allowed, decision_status = policy.authorize(conf, path, method, token, function(value, audience, permission)
    return kc.decide(conf, value, audience, permission)
  end)
  if not allowed then return fail(decision_status) end
  -- Never let a shared service credential cause an application to bypass user checks.
  api.service.request.clear_header("x-internal-service-token")
  api.service.request.clear_header("x-internal-token")
  api.service.request.set_header("authorization", "Bearer " .. token)
  if not set_gateway_identity(conf, claims) then return fail(401) end
end

return Handler
end
return M
