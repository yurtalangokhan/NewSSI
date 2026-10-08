-- Headless SP -> external IdP broker login.
--
-- The login page's "external" username/password form must not bounce the user to
-- the external IdP's own login page. The gateway therefore walks the Keycloak
-- broker flow server-side: SP authorize (kc_idp_hint) -> external IdP login form
-- -> post credentials -> broker callback -> redirect_uri?code=... The caller then
-- exchanges the code (PKCE) with the SP realm like any other login.
local M = {}

local MAX_STEPS = 20
local FAILURE_STATUS = {idp_error = 403, state_mismatch = 401}
local REDIRECTS = {[301] = true, [302] = true, [303] = true, [307] = true, [308] = true}
local ENTITIES = {amp = "&", lt = "<", gt = ">", quot = '"', apos = "'"}

local function trim(value)
  return (value:gsub("^%s+", ""):gsub("%s+$", ""))
end

function M.unescape(value)
  value = value:gsub("&#([xX]?)(%x+);", function(hex, digits)
    local code = hex ~= "" and tonumber(digits, 16) or tonumber(digits)
    if code and code > 0 and code < 128 then return string.char(code) end
  end)
  return (value:gsub("&(%a+);", ENTITIES))
end

function M.origin(url)
  local origin = type(url) == "string" and url:match("^(https?://[^/?#]+)")
  return origin and origin:lower() or nil
end

local function path_of(url)
  local path = url:match("^https?://[^/?#]+([^?#]*)")
  return (path and path ~= "") and path or "/"
end

function M.join(base, ref)
  if ref:match("^https?://") then return ref end
  local origin = base:match("^(https?://[^/?#]+)")
  if ref:sub(1, 2) == "//" then return base:match("^(https?:)") .. ref end
  if ref:sub(1, 1) == "/" then return origin .. ref end
  local without_query = base:gsub("[?#].*$", "")
  if ref:sub(1, 1) == "?" then return without_query .. ref end
  return origin .. path_of(without_query):match("^(.*/)") .. ref
end

function M.rewrite(rewrites, url)
  for public, backend in pairs(rewrites or {}) do
    if public ~= "" and url:sub(1, #public) == public then
      return backend .. url:sub(#public + 1)
    end
  end
  return url
end

-- Path-aware, host-only cookie jar. The SP and external realms may live on the
-- same Keycloak host, where both set AUTH_SESSION_ID under different paths.
function M.store(jar, url, headers)
  if type(headers) == "string" then headers = {headers} end
  local origin = M.origin(url)
  for _, header in ipairs(type(headers) == "table" and headers or {}) do
    local pair, attributes = header:match("^([^;]*)(.*)$")
    local name, value = pair:match("^%s*([^=%s]+)%s*=(.*)$")
    if name then
      local lower = attributes:lower()
      local path = lower:match(";%s*path=") and trim(attributes:match(";%s*[Pp][Aa][Tt][Hh]=([^;]*)")) or nil
      if not path or path:sub(1, 1) ~= "/" then
        path = path_of(url):match("^(.*)/") or ""
        if path == "" then path = "/" end
      end
      local max_age = tonumber(lower:match(";%s*max%-age=%s*(%-?%d+)"))
      local expired = (max_age and max_age <= 0) or lower:match(";%s*expires=[^;]*1970") ~= nil
      local kept = {}
      for _, cookie in ipairs(jar) do
        if not (cookie.origin == origin and cookie.path == path and cookie.name == name) then
          kept[#kept + 1] = cookie
        end
      end
      if not expired then
        kept[#kept + 1] = {origin = origin, path = path, name = name, value = trim(value)}
      end
      for index = #jar, 1, -1 do jar[index] = nil end
      for index, cookie in ipairs(kept) do jar[index] = cookie end
    end
  end
end

local function path_matches(request_path, cookie_path)
  if request_path == cookie_path then return true end
  if request_path:sub(1, #cookie_path) ~= cookie_path then return false end
  return cookie_path:sub(-1) == "/" or request_path:sub(#cookie_path + 1, #cookie_path + 1) == "/"
end

function M.cookie_header(jar, url)
  local origin, path, matches = M.origin(url), path_of(url), {}
  for _, cookie in ipairs(jar) do
    if cookie.origin == origin and path_matches(path, cookie.path) then
      matches[#matches + 1] = cookie
    end
  end
  table.sort(matches, function(a, b) return #a.path > #b.path end)
  local parts = {}
  for _, cookie in ipairs(matches) do parts[#parts + 1] = cookie.name .. "=" .. cookie.value end
  return #parts > 0 and table.concat(parts, "; ") or nil
end

local function attribute(tag, wanted)
  for name, _, value in tag:gmatch("([%w_:%-]+)%s*=%s*([\"'])(.-)%2") do
    if name:lower() == wanted then return M.unescape(value) end
  end
end

-- First <form> that has an action, with its named <input> values (mirrors the
-- former user-service parser).
function M.login_form(html, page_url)
  local lower, position = html:lower(), 1
  while true do
    local start, finish = lower:find("<form[%s>]", position)
    if not start then return nil end
    local tag_end = lower:find(">", start, true)
    if not tag_end then return nil end
    local closing = lower:find("</form>", tag_end, true) or #html
    local action = attribute(html:sub(start, tag_end), "action")
    if action and action ~= "" then
      local inputs, body = {}, html:sub(tag_end + 1, closing - 1)
      for tag in body:gmatch("<[Ii][Nn][Pp][Uu][Tt][^>]*>") do
        local input_name = attribute(tag, "name")
        if input_name and input_name ~= "" then inputs[input_name] = attribute(tag, "value") or "" end
      end
      return M.join(page_url, action), inputs
    end
    position = math.max(finish, closing)
  end
end

function M.callback(url, state)
  local query = url:match("%?([^#]*)")
  local args = query and ngx.decode_args(query) or {}
  if type(args.error) == "string" then return nil, "idp_error" end
  if type(args.code) ~= "string" or args.code == "" then return nil end
  if args.state ~= state then return nil, "state_mismatch" end
  return args.code
end

local function header(res, name)
  local value = res.headers and res.headers[name]
  if type(value) == "table" then return value[1] end
  return value
end

-- Returns code on success, or nil, http_status, reason.
function M.password_login(conf, authorize_url, redirect_uri, state, username, password, http_client)
  local client = http_client or require("resty.http").new()
  client:set_timeout(10000)
  local jar = {}

  local function fetch(method, url, body)
    local target = M.rewrite(conf.broker_url_rewrites, url)
    if not M.origin(target) then return nil, "invalid_url" end
    local headers = {["User-Agent"] = "AgenticAI-Gateway/1.0", Accept = "text/html,application/xhtml+xml"}
    local cookies = M.cookie_header(jar, target)
    if cookies then headers.Cookie = cookies end
    if body then headers["Content-Type"] = "application/x-www-form-urlencoded" end
    local res, err = client:request_uri(target, {
      method = method, headers = headers, body = body, ssl_verify = true,
    })
    if not res then return nil, "unreachable: " .. tostring(err) end
    M.store(jar, target, res.headers and res.headers["Set-Cookie"])
    return res, target
  end

  -- Follows redirects until the SP hands back a code or a page renders.
  local function follow(res, url)
    for _ = 1, MAX_STEPS do
      if not REDIRECTS[res.status] then
        if res.status == 200 then return nil, nil, res, url end
        return nil, "unexpected_status_" .. res.status
      end
      local location = header(res, "Location")
      if not location then return nil, "redirect_without_location" end
      local absolute = M.join(url, M.unescape(location))
      if absolute:sub(1, #redirect_uri) == redirect_uri then
        -- Never fetch the application callback itself; it only carries the code.
        local code, err = M.callback(absolute, state)
        if code then return code end
        return nil, err or "callback_without_code"
      end
      local next_res, next_url = fetch("GET", absolute)
      if not next_res then return nil, next_url end
      res, url = next_res, next_url
    end
    return nil, "too_many_redirects"
  end

  local res, url = fetch("GET", authorize_url)
  if not res then return nil, 503, url end
  local code, err, page, page_url = follow(res, url)
  if code then return code end
  if err then return nil, FAILURE_STATUS[err] or 503, err end

  local action, inputs = M.login_form(page.body or "", page_url)
  if not action then return nil, 503, "login_form_not_found" end
  -- An unknown/disabled IdP hint can leave us on the SP's own login form.
  -- Do not authenticate internal users through the external login endpoint.
  local sp_realm = M.rewrite(conf.broker_url_rewrites, authorize_url)
    :match("^(.-)/protocol/openid%-connect/auth")
  local target_action = M.rewrite(conf.broker_url_rewrites, action)
  if sp_realm and (page_url:sub(1, #sp_realm + 1) == sp_realm .. "/" or
      target_action:sub(1, #sp_realm + 1) == sp_realm .. "/") then
    return nil, 503, "external_idp_not_reached"
  end
  -- Never post credentials to a host other than the page that asked for them.
  if M.origin(target_action) ~= M.origin(page_url) then
    return nil, 503, "login_form_cross_origin"
  end
  inputs.username, inputs.password = username, password
  res, url = fetch("POST", action, ngx.encode_args(inputs))
  if not res then return nil, 503, url end
  code, err, page, page_url = follow(res, url)
  if code then return code end
  if err then return nil, FAILURE_STATUS[err] or 503, err end
  -- A page rendered instead of a redirect. If it asks for a password again the
  -- IdP rejected the credentials; anything else (first-broker-login, required
  -- actions) needs the interactive browser flow.
  local _, retry_inputs = M.login_form(page.body or "", page_url)
  if retry_inputs and retry_inputs.password ~= nil then
    return nil, 401, "credentials_rejected"
  end
  return nil, 409, "interactive_step_required"
end

return M
