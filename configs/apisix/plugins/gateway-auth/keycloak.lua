local http = require "resty.http"
local json = require "cjson.safe"
local M = {}

function M.request(conf, endpoint, form, bearer)
  local client = http.new()
  client:set_timeout(5000)
  local headers = {Accept = "application/json"}
  if bearer then headers.Authorization = "Bearer " .. bearer end
  if form then headers["Content-Type"] = "application/x-www-form-urlencoded" end
  local response = client:request_uri(conf.keycloak_base_url .. "/protocol/openid-connect/" .. endpoint, {
    method = form and "POST" or "GET", headers = headers,
    body = form and ngx.encode_args(form), ssl_verify = true,
    keepalive = true,
  })
  if not response then return nil, 503 end
  local data = json.decode(response.body)
  if response.status >= 500 then return nil, 503 end
  if response.status < 200 or response.status >= 300 then
    return nil, response.status == 403 and 403 or 401
  end
  if response.status == 204 then return {}, 204 end
  if type(data) ~= "table" then return nil, 503 end
  return data, response.status
end

function M.valid_claims(conf, data, now)
  if type(data) ~= "table" or data.active ~= true or data.token_type ~= "Bearer" or type(data.sub) ~= "string" or
      data.sub == "" or data.iss ~= conf.issuer_url or
      type(data.exp) ~= "number" or data.exp <= now or
      (data.nbf ~= nil and (type(data.nbf) ~= "number" or data.nbf > now)) then return false end
  local audience = data.aud
  if type(audience) == "string" then audience = {audience} end
  if type(audience) ~= "table" then return false end
  for _, item in ipairs(audience) do
    if item == conf.introspection_client_id then return true end
  end
  return false
end

function M.introspect(conf, token)
  local claims, status = M.request(conf, "token/introspect", {
    token = token, token_type_hint = "access_token",
    client_id = conf.introspection_client_id,
    client_secret = conf.introspection_client_secret,
  })
  if not claims then return nil, status end
  if not M.valid_claims(conf, claims, ngx.time()) then return nil, 401 end
  return claims
end

function M.decide(conf, token, audience, permission)
  if not audience or type(permission) ~= "string" or not permission:find("#", 1, true) then
    return false, 403
  end
  local result, status = M.request(conf, "token", {
    grant_type = "urn:ietf:params:oauth:grant-type:uma-ticket", audience = audience,
    permission = permission, response_mode = "decision",
  }, token)
  return result ~= nil and result.result == true, status == 503 and 503 or 403
end

function M.exchange(conf, form)
  form.client_id = conf.login_client_id
  if conf.login_client_secret and conf.login_client_secret ~= "" then
    form.client_secret = conf.login_client_secret
  end
  return M.request(conf, "token", form)
end

return M
