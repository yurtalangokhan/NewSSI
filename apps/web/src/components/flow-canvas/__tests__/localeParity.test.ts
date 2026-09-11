import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";

describe("Task 52 — i18n locale parity and template overrides", () => {
  it("52.1 — flowCanvas namespace exists in both en and tr locales", () => {
    expect((en as any).flowCanvas).toBeDefined();
    expect((tr as any).flowCanvas).toBeDefined();
  });

  it("52.2 — sidebar, versionBar, inspector, validation, controls subnamespaces have parity", () => {
    const enFlow = (en as any).flowCanvas;
    const trFlow = (tr as any).flowCanvas;

    const sections = [
      "sidebar",
      "versionBar",
      "inspector",
      "validation",
      "controls",
      "playground",
      "fields",
      "nodeToolbar",
      "stickyNote",
    ];
    for (const section of sections) {
      expect(enFlow[section]).toBeDefined();
      expect(trFlow[section]).toBeDefined();

      const enKeys = Object.keys(enFlow[section]);
      const trKeys = Object.keys(trFlow[section]);
      expect(trKeys.sort()).toEqual(enKeys.sort());
    }
  });

  // 52.6-52.8 removed with `templateTextOverrides.ts`: a hardcoded EN/TR copy
  // of display_name/description that no production code read. The canvas gets
  // its copy from `flowCanvas.components.<type>` with the server's
  // `display_name` as the i18n fallback — see ComponentSidebarItem,
  // TemplateNode, NodeInspector, componentSearch and GraphStageStrip.

  it("52.9 — the Set Variable node has en and tr catalog copy", () => {
    for (const locale of [en, tr] as any[]) {
      const entry = locale.flowCanvas.components.SetVariable;
      expect(entry).toBeDefined();
      expect(entry.name).toBeTruthy();
      expect(entry.description).toBeTruthy();
    }
  });

  it("52.10 — the Smart Router node has en and tr catalog copy", () => {
    for (const locale of [en, tr] as any[]) {
      const entry = locale.flowCanvas.components.SmartRouter;
      expect(entry).toBeDefined();
      expect(entry.name).toBeTruthy();
      expect(entry.description).toBeTruthy();
    }
  });

  it("52.11 — the While node (renamed counter loop) has en and tr catalog copy", () => {
    for (const locale of [en, tr] as any[]) {
      const entry = locale.flowCanvas.components.While;
      expect(entry).toBeDefined();
      expect(entry.name).toBeTruthy();
      expect(entry.description).toBeTruthy();
    }
  });

  it("52.12 — the Human Input node has en and tr catalog copy", () => {
    for (const locale of [en, tr] as any[]) {
      const entry = locale.flowCanvas.components.HumanInput;
      expect(entry).toBeDefined();
      expect(entry.name).toBeTruthy();
      expect(entry.description).toBeTruthy();
    }
  });

  it("52.13 — importErrors has en/tr parity and no empty values", () => {
    const codes = ["invalidJson", "notAnObject", "missingSpec", "noNodes"];
    for (const locale of [en, tr] as any[]) {
      const block = locale.flowCanvas.importErrors;
      expect(block).toBeDefined();
      for (const c of codes) expect(block[c]).toBeTruthy();
      expect(Object.keys(block).sort()).toEqual([...codes].sort());
    }
  });

  it("52.14 — new playground + versionBar fallback keys exist in both locales", () => {
    for (const locale of [en, tr] as any[]) {
      const pg = locale.flowCanvas.playground;
      expect(pg.runFailedWithStatus).toBeTruthy();
      expect(pg.noResponseStream).toBeTruthy();
      expect(pg.networkError).toBeTruthy();
      expect(locale.flowCanvas.versionBar.publishedConcurrently).toBeTruthy();
    }
  });

  it("52.15 — flowCanvas.tools covers every BUILTIN_CATEGORY_TOOLS value in both locales", () => {
    // Guards A1: useFieldOptions.translateOption() resolves each row through
    // flowCanvas.tools.<value>.{label,description}; the English strings in the
    // table are only the i18n fallback. BUILTIN_CATEGORY_TOOLS is module-private,
    // so assert against its value list (kept in sync by this test failing).
    const values = [
      "calculate",
      "execute_python_code",
      "execute_bash_command",
      "validate_python_syntax",
      "format_python_code",
      "install_package",
      "list_installed_packages",
      "execute_command",
      "ping_host",
      "get_system_info",
      "list_containers",
      "inspect_container",
      "get_container_logs",
      "start_container",
      "stop_container",
      "restart_container",
      "list_images",
      "read_file",
      "write_file",
      "append_to_file",
      "list_directory",
      "file_exists",
      "delete_file",
      "create_directory",
      "get_file_info",
      "search_files",
      "git_status",
      "git_diff",
      "git_log",
      "git_add",
      "git_commit",
      "git_checkout",
      "git_branch",
      "git_clone",
      "git_pull",
      "compile_java",
      "run_java_class",
      "run_jar",
      "inspect_class",
      "get_jvm_info",
      "list_classpath",
      "parse_json",
      "validate_json",
      "format_json",
      "query_json",
      "json_diff",
      "send_email",
      "draft_email",
      "search_emails",
      "read_email",
      "extract_text",
      "extract_pages",
      "get_metadata",
      "render_page_as_image",
      "search_pdf",
      "check_health",
      "list_endpoints",
      "call_endpoint",
      "count_words",
      "summarize_text",
      "regex_match",
      "regex_replace",
      "convert_case",
      "split_text",
      "get_current_time",
      "format_date",
      "calculate_duration",
      "generate_uuid",
      "hash_text",
      "base64_encode",
      "base64_decode",
      "random_number",
      "web_search",
      "fetch_webpage",
      "scrape_content",
      "crawl_sitemap",
    ];
    for (const locale of [en, tr] as any[]) {
      for (const v of values) {
        const entry = locale.flowCanvas.tools[v];
        expect(entry?.label).toBeTruthy();
        expect(entry?.description).toBeTruthy();
      }
    }
  });
});
