local core = require "apisix.core"
local json = require "cjson.safe"
local handler = require "apisix.plugins.gateway-auth.handler"

local schema = {
  type = "object",
  properties = {
    mode = {type = "string", enum = {"auth", "protected", "internal"}},
    issuer_url = {type = "string", minLength = 1},
    keycloak_base_url = {type = "string", minLength = 1},
    login_client_id = {type = "string", minLength = 1},
    login_client_secret = {type = "string"},
    introspection_client_id = {type = "string", minLength = 1},
    introspection_client_secret = {type = "string", minLength = 1},
    policy_file = {type = "string", default = "/usr/local/apisix/conf/gateway-policies.json"},
    allowed_redirect_uris = {type = "array", items = {type = "string"}},
    cookie_secure = {type = "boolean", default = true},
    external_idp_alias = {type = "string"},
    broker_url_rewrites = {type = "object", additionalProperties = {type = "string"}, default = {}},
    redis_host = {type = "string", minLength = 1},
    redis_port = {type = "integer", minimum = 1, maximum = 65535, default = 6379},
    redis_password = {type = "string"},
    redis_database = {type = "integer", minimum = 0, default = 0},
    internal_service_token = {type = "string", minLength = 1},
  },
  required = {"mode", "issuer_url", "keycloak_base_url", "login_client_id",
    "introspection_client_id", "introspection_client_secret", "allowed_redirect_uris",
    "redis_host", "internal_service_token"},
}

local M = {version = 1.0, priority = 1015, name = "gateway-auth", schema = schema}

function M.check_schema(conf)
  return core.schema.check(schema, conf)
end

-- Each request owns its transport. Never publish request state in a worker global.
local function transport(ctx)
  local function header(name)
    -- core.request.header collapses arrays; retain duplicate credentials so the
    -- authentication handler can reject ambiguous Authorization headers.
    return core.request.headers(ctx)[name]
  end
  local function body()
    local content_type = header("content-type")
    if type(content_type) ~= "string" then return nil end
    local media_type = content_type:match("^%s*([^; ]+)")
    media_type = media_type and media_type:lower()
    -- get_body also reads bodies buffered to disk, unlike get_post_args.
    local raw = core.request.get_body(nil, ctx)
    if type(raw) ~= "string" then return nil end
    if media_type == "application/json" then
      local decoded = json.decode(raw)
      return type(decoded) == "table" and decoded or nil
    end
    if media_type == "application/x-www-form-urlencoded" then
      local decoded, err = ngx.decode_args(raw)
      if err then return nil end
      return decoded
    end
  end
  return {
    request = {
      get_header = header,
      get_body = body,
      get_path = function() return ctx.var.uri end,
      get_method = core.request.get_method,
      get_query = function() return core.request.get_uri_args(ctx) end,
    },
    service = {request = {
      set_header = function(name, value) core.request.set_header(ctx, name, value) end,
      clear_header = function(name) core.request.set_header(ctx, name, nil) end,
    }},
    response = {exit = function(status, payload, headers)
      for name, value in pairs(headers or {}) do ngx.header[name] = value end
      return status, payload
    end},
    log = core.log,
  }
end

-- Run before proxy-rewrite (1008), which changes the URI used by our policies.
-- APISIX owns response termination when rewrite returns a status and body.
function M.rewrite(conf, ctx)
  return handler.new(transport(ctx)):access(conf)
end

return M
