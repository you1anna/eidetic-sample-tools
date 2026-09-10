// Eidetic isolated extension. Upstream handlers remain unchanged.
// Song.file_path/name: https://docs.cycling74.com/apiref/lom/song/
var EIDETIC_BUILD_ID = "__EIDETIC_BUILD_ID__";
var eideticInstanceId = String(new Date().getTime()) + "-" + String(Math.random()).slice(2);
var eideticUpstreamGet = api_get;
api_get = function(path, property, requestId) {
  if (String(path) !== "live_set" || String(property) !== "eidetic_runtime") {
    return eideticUpstreamGet(path, property, requestId);
  }
  if (!ensureInitialized(requestId)) return;
  try {
    var current = new LiveAPI(null, "live_set");
    var identity = {
      build_id: EIDETIC_BUILD_ID,
      instance_id: eideticInstanceId,
      set_id: Number(current.id),
      set_path: String(getScalar(current, "file_path")),
      set_name: String(getScalar(current, "name"))
    };
    ackWithRequest("api_get", ["live_set", "eidetic_runtime", JSON.stringify(identity)], requestId);
  } catch (err) {
    ackWithRequest("error", ["eidetic_identity_unavailable"], requestId);
  }
};
API_FALLBACK_HANDLERS.api_get = api_get;

// Max can return a named Dict reference as ["dictionary", name]. Resolve the
// reference without clearing it (Live owns it); the upstream bounded ACK path
// still enforces its response-size and elapsed-time limits.
var eideticUpstreamValueToJson = liveApiValueToJson;
liveApiValueToJson = function(value, contextName) {
  if (Array.isArray(value) && value.length === 2 && String(value[0]) === "dictionary") {
    var referenced = new Dict(String(value[1]));
    var encoded = referenced.stringify();
    if (!encoded) throw new Error("eidetic_empty_dictionary_reference");
    JSON.parse(encoded);
    return encoded;
  }
  return eideticUpstreamValueToJson(value, contextName);
};
