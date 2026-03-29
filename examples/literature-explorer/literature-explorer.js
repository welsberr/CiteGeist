export function createLiteratureExplorerClient(bridge) {
  return {
    capabilities() {
      return bridge.call("capabilities", {});
    },
    search(query, options = {}) {
      return bridge.call("search", { query, ...options });
    },
    showEntry(citationKey, options = {}) {
      return bridge.call("show_entry", { citation_key: citationKey, ...options });
    },
    listTopics(options = {}) {
      return bridge.call("list_topics", options);
    },
    getTopic(topicSlug, options = {}) {
      return bridge.call("get_topic", { topic_slug: topicSlug, ...options });
    },
    bootstrap(options = {}) {
      return bridge.call("bootstrap", options);
    },
    expandTopic(topicSlug, options = {}) {
      return bridge.call("expand_topic", { topic_slug: topicSlug, ...options });
    },
    extractText(text, options = {}) {
      return bridge.call("extract_text", { text, ...options });
    },
    verifyStrings(values, options = {}) {
      return bridge.call("verify_strings", { values, ...options });
    },
    verifyBibtex(bibtexText, options = {}) {
      return bridge.call("verify_bibtex", { bibtex_text: bibtexText, ...options });
    },
    graph(seedKeys, options = {}) {
      return bridge.call("graph", { seed_keys: seedKeys, ...options });
    },
  };
}

export function createHttpBridge(baseUrl = "http://127.0.0.1:8765") {
  return {
    async call(method, params = {}) {
      const response = await fetch(`${baseUrl}/call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method, params }),
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || `Request failed: ${response.status}`);
      }
      return payload.result;
    },
  };
}
