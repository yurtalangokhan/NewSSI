local json = require "cjson.safe"
local M = {}
local files = {}

function M.match(conf, path, method)
  local policies = conf.policies
  if not policies then
    policies = files[conf.policy_file]
    if not policies then
      local file = io.open(conf.policy_file or "", "r")
      if not file then return nil end
      local data = file:read("*a"); file:close()
      policies = json.decode(data)
      if type(policies) ~= "table" then return nil end
      files[conf.policy_file] = policies
    end
  end
  for _, rule in ipairs(policies) do
    for _, verb in ipairs(rule.methods or {}) do
      if verb == method and type(rule.path) == "string" and
          rule.path:sub(1, 1) == "^" and rule.path:sub(-1) == "$" and
          ngx.re.find(path, rule.path, "jo") then
        return rule
      end
    end
  end
end

function M.authorize(conf, path, method, token, decide)
  local rule = M.match(conf, path, method)
  if not rule then return false, 403 end
  local permissions = rule.permissions or {}
  if #permissions == 0 then return rule.authenticated_only == true, 403 end
  for _, permission in ipairs(permissions) do
    local allowed, status = decide(token, rule.audience, permission)
    if allowed ~= true then return false, status or 403 end
  end
  return true
end

return M
