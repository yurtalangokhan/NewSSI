local redis = require "resty.redis"
local random = require "resty.random"
local str = require "resty.string"
local sha256 = require "resty.sha256"
local json = require "cjson.safe"
local M = {}

local function connection(conf)
  local client = redis:new()
  client:set_timeout(3000)
  local ok = client:connect(conf.redis_host, conf.redis_port)
  if not ok then return nil end
  if conf.redis_password and conf.redis_password ~= "" then
    if not client:auth(conf.redis_password) then client:close(); return nil end
  end
  if conf.redis_database and conf.redis_database ~= 0 then
    if not client:select(conf.redis_database) then client:close(); return nil end
  end
  return client
end

function M.random()
  local bytes = random.bytes(32, true)
  if not bytes then return nil end
  return str.to_hex(bytes)
end

function M.challenge(verifier)
  local digest = sha256:new()
  digest:update(verifier)
  return ngx.encode_base64(digest:final()):gsub("+", "-"):gsub("/", "_"):gsub("=", "")
end

function M.save(conf, state, value)
  local client = connection(conf)
  if not client then return nil end
  local ok = client:set("gateway:oidc:" .. state, json.encode(value), "EX", 300, "NX")
  client:set_keepalive(10000, 100)
  return ok == "OK"
end

function M.consume(conf, state, binding)
  if type(state) ~= "string" or #state > 128 or type(binding) ~= "string" then return nil end
  local client = connection(conf)
  if not client then return nil, 503 end
  local value, err = client:eval([[
    local value = redis.call('GET', KEYS[1])
    if not value then return nil end
    local session = cjson.decode(value)
    if session.binding ~= ARGV[1] then return nil end
    redis.call('DEL', KEYS[1])
    return value
  ]], 1, "gateway:oidc:" .. state, binding)
  client:set_keepalive(10000, 100)
  if err then return nil, 503 end
  if not value or value == ngx.null then return nil, 401 end
  local decoded = json.decode(value)
  if type(decoded) ~= "table" then return nil, 401 end
  return decoded
end

return M
