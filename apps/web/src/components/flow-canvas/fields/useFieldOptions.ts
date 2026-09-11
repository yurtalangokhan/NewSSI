import { isEmbeddingModel } from "@/lib/llmConfig/modelClassification";
/**
 * Shared by OptionsField and MultiselectField: resolves a field's option
 * list from whichever source P1 guarantees is present
 * (`_check_choices_available` — `options` or `options_source`, never
 * neither).
 */

import { useTranslation } from "react-i18next";
import { useResolvedOptions } from "../hooks/useResolvedOptions";
import { dependencyValues } from "./optionDependencies";
import type { InputField } from "../types/componentTemplate";

export type ResolvedOption = {
  value: string;
  label: string;
  description?: string | null;
};

export type FieldOptionsResult = {
  options: ResolvedOption[];
  isLoading: boolean;
  unavailable: boolean;
};

/* eslint-disable no-restricted-syntax -- rows are resolved at runtime through
   translateOption() → flowCanvas.tools.<value>.{label,description}; the English
   strings here are only the i18n fallback. Parity guarded by localeParity.test
   (52.15). `label` stays the technical tool identifier by product decision. */
const BUILTIN_CATEGORY_TOOLS: Record<string, ResolvedOption[]> = {
  calculator: [
    {
      value: "calculate",
      label: "Calculate",
      description: "Safe mathematical expression evaluation",
    },
  ],
  code: [
    {
      value: "execute_python_code",
      label: "Execute Python Code",
      description: "Execute Python code in a secure sandbox",
    },
    {
      value: "execute_bash_command",
      label: "Execute Bash Command",
      description: "Execute a bash command in a secure sandbox",
    },
    {
      value: "validate_python_syntax",
      label: "Validate Python Syntax",
      description: "Check Python code for syntax errors",
    },
    {
      value: "format_python_code",
      label: "Format Python Code",
      description: "Format Python code using Black",
    },
    {
      value: "install_package",
      label: "Install Package",
      description: "Install a Python package via pip",
    },
    {
      value: "list_installed_packages",
      label: "List Installed Packages",
      description: "List all installed Python packages",
    },
  ],
  command: [
    {
      value: "execute_command",
      label: "Execute Command",
      description: "Execute system command",
    },
    {
      value: "ping_host",
      label: "Ping Host",
      description: "Ping a network host",
    },
    {
      value: "get_system_info",
      label: "Get System Info",
      description: "Get system hardware and OS information",
    },
  ],
  docker: [
    {
      value: "list_containers",
      label: "List Containers",
      description: "List Docker containers",
    },
    {
      value: "inspect_container",
      label: "Inspect Container",
      description: "Get detailed container information",
    },
    {
      value: "get_container_logs",
      label: "Get Container Logs",
      description: "Get logs from a container",
    },
    {
      value: "start_container",
      label: "Start Container",
      description: "Start a stopped container",
    },
    {
      value: "stop_container",
      label: "Stop Container",
      description: "Stop a running container",
    },
    {
      value: "restart_container",
      label: "Restart Container",
      description: "Restart a container",
    },
    {
      value: "list_images",
      label: "List Images",
      description: "List local Docker images",
    },
  ],
  file: [
    {
      value: "read_file",
      label: "Read File",
      description: "Read contents of a file",
    },
    {
      value: "write_file",
      label: "Write File",
      description: "Write content to a file",
    },
    {
      value: "append_to_file",
      label: "Append to File",
      description: "Append content to a file",
    },
    {
      value: "list_directory",
      label: "List Directory",
      description: "List files and directories in a path",
    },
    {
      value: "file_exists",
      label: "File Exists",
      description: "Check if a file or directory exists",
    },
    {
      value: "delete_file",
      label: "Delete File",
      description: "Delete a file",
    },
    {
      value: "create_directory",
      label: "Create Directory",
      description: "Create a new directory",
    },
    {
      value: "get_file_info",
      label: "Get File Info",
      description: "Get metadata for a file or directory",
    },
    {
      value: "search_files",
      label: "Search Files",
      description: "Search for files matching a pattern",
    },
  ],
  git: [
    {
      value: "git_status",
      label: "Git Status",
      description: "Get current working tree status",
    },
    {
      value: "git_diff",
      label: "Git Diff",
      description: "Show changes between commits and working tree",
    },
    { value: "git_log", label: "Git Log", description: "Show commit logs" },
    {
      value: "git_add",
      label: "Git Add",
      description: "Add file contents to the staging area",
    },
    {
      value: "git_commit",
      label: "Git Commit",
      description: "Record changes to the repository",
    },
    {
      value: "git_checkout",
      label: "Git Checkout",
      description: "Switch branches or restore working tree files",
    },
    {
      value: "git_branch",
      label: "Git Branch",
      description: "List, create, or delete branches",
    },
    {
      value: "git_clone",
      label: "Git Clone",
      description: "Clone a repository into a new directory",
    },
    {
      value: "git_pull",
      label: "Git Pull",
      description: "Fetch from and integrate with another repository",
    },
  ],
  java: [
    {
      value: "compile_java",
      label: "Compile Java",
      description: "Compile Java source files",
    },
    {
      value: "run_java_class",
      label: "Run Java Class",
      description: "Execute a compiled Java class",
    },
    {
      value: "run_jar",
      label: "Run JAR",
      description: "Execute a runnable JAR file",
    },
    {
      value: "inspect_class",
      label: "Inspect Class",
      description: "Disassemble/inspect a Java class",
    },
    {
      value: "get_jvm_info",
      label: "Get JVM Info",
      description: "Get Java Virtual Machine information",
    },
    {
      value: "list_classpath",
      label: "List Classpath",
      description: "List JARs and classes on the classpath",
    },
  ],
  json: [
    {
      value: "parse_json",
      label: "Parse JSON",
      description: "Parse a JSON string into a structured object",
    },
    {
      value: "validate_json",
      label: "Validate JSON",
      description: "Validate JSON syntax and structure",
    },
    {
      value: "format_json",
      label: "Format JSON",
      description: "Pretty-print JSON with indentation",
    },
    {
      value: "query_json",
      label: "Query JSON",
      description: "Query JSON using JSONPath expressions",
    },
    {
      value: "json_diff",
      label: "JSON Diff",
      description: "Compare two JSON objects and find differences",
    },
  ],
  mail: [
    {
      value: "send_email",
      label: "Send Email",
      description: "Send an email via configured SMTP",
    },
    {
      value: "draft_email",
      label: "Draft Email",
      description: "Create an email draft",
    },
    {
      value: "search_emails",
      label: "Search Emails",
      description: "Search email inbox by query",
    },
    {
      value: "read_email",
      label: "Read Email",
      description: "Read full email content and attachments",
    },
  ],
  pdf: [
    {
      value: "extract_text",
      label: "Extract Text",
      description: "Extract all text from a PDF document",
    },
    {
      value: "extract_pages",
      label: "Extract Pages",
      description: "Extract specific page range from a PDF",
    },
    {
      value: "get_metadata",
      label: "Get Metadata",
      description: "Get title, author, and page count of PDF",
    },
    {
      value: "render_page_as_image",
      label: "Render Page Image",
      description: "Render a PDF page to PNG/JPEG",
    },
    {
      value: "search_pdf",
      label: "Search PDF",
      description: "Search for text occurrences within PDF",
    },
  ],
  service: [
    {
      value: "check_health",
      label: "Check Health",
      description: "Check health of a web service",
    },
    {
      value: "list_endpoints",
      label: "List Endpoints",
      description: "List discovered REST endpoints",
    },
    {
      value: "call_endpoint",
      label: "Call Endpoint",
      description: "Make HTTP request to service endpoint",
    },
  ],
  text: [
    {
      value: "count_words",
      label: "Count Words",
      description: "Count words, characters, and sentences",
    },
    {
      value: "summarize_text",
      label: "Summarize Text",
      description: "Generate concise summary of text",
    },
    {
      value: "regex_match",
      label: "Regex Match",
      description: "Match regular expression against text",
    },
    {
      value: "regex_replace",
      label: "Regex Replace",
      description: "Replace patterns using regular expressions",
    },
    {
      value: "convert_case",
      label: "Convert Case",
      description: "Convert text case (upper, lower, title, camel)",
    },
    {
      value: "split_text",
      label: "Split Text",
      description: "Split text into chunks or tokens",
    },
  ],
  time: [
    {
      value: "get_current_time",
      label: "Get Current Time",
      description: "Get current date and time with timezone",
    },
    {
      value: "format_date",
      label: "Format Date",
      description: "Format timestamps into standard string formats",
    },
    {
      value: "calculate_duration",
      label: "Calculate Duration",
      description: "Calculate difference between two dates",
    },
  ],
  utility: [
    {
      value: "generate_uuid",
      label: "Generate UUID",
      description: "Generate random UUID v4 string",
    },
    {
      value: "hash_text",
      label: "Hash Text",
      description: "Compute SHA-256 or MD5 hash of text",
    },
    {
      value: "base64_encode",
      label: "Base64 Encode",
      description: "Encode string or bytes to base64",
    },
    {
      value: "base64_decode",
      label: "Base64 Decode",
      description: "Decode base64 string to original text",
    },
    {
      value: "random_number",
      label: "Random Number",
      description: "Generate cryptographically secure random number",
    },
  ],
  web: [
    {
      value: "web_search",
      label: "Web Search",
      description: "Search the web using configured search provider",
    },
    {
      value: "fetch_webpage",
      label: "Fetch Webpage",
      description: "Fetch and extract text from a webpage URL",
    },
    {
      value: "scrape_content",
      label: "Scrape Content",
      description: "Extract structured data from a webpage",
    },
    {
      value: "crawl_sitemap",
      label: "Crawl Sitemap",
      description: "Parse and crawl links from a sitemap",
    },
  ],
};
/* eslint-enable no-restricted-syntax */

export function useFieldOptions(
  field: InputField,
  allValues?: Record<string, unknown>
): FieldOptionsResult {
  const { t } = useTranslation();
  const translateOption = (o: ResolvedOption): ResolvedOption => ({
    value: o.value,
    label: t(`flowCanvas.tools.${o.value}.label`, o.label),
    description: o.description
      ? t(`flowCanvas.tools.${o.value}.description`, o.description)
      : o.description,
  });
  const hasStaticOptions = field.options != null;
  const resolved = useResolvedOptions(
    hasStaticOptions ? null : field.options_source,
    dependencyValues(field, allValues)
  );

  if (hasStaticOptions) {
    return {
      options: field.options!.map((o) =>
        translateOption({ value: o, label: o })
      ),
      isLoading: false,
      unavailable: false,
    };
  }

  const source = field.options_source;
  const cat = source?.startsWith("mcp.tools.")
    ? source.replace("mcp.tools.", "")
    : null;
  const builtinOptions = cat ? BUILTIN_CATEGORY_TOOLS[cat] : null;

  if (resolved.data?.items && resolved.data.items.length > 0) {
    const isLlmSource = source === "llm.models" || source === "ollama.models";
    const filteredItems = isLlmSource
      ? resolved.data.items.filter(
          // Belt-and-braces: the resolver already drops embedding models, but a
          // resolved item may still carry capability metadata beyond the
          // declared value/label/description shape.
          (item) =>
            !isEmbeddingModel(item as Parameters<typeof isEmbeddingModel>[0])
        )
      : resolved.data.items;

    return {
      options: filteredItems.map(translateOption),
      isLoading: false,
      unavailable: !resolved.data.available,
    };
  }

  if (builtinOptions) {
    return {
      options: builtinOptions.map(translateOption),
      isLoading: false,
      unavailable: false,
    };
  }

  return {
    options: (resolved.data?.items ?? []).map(translateOption),
    isLoading: resolved.isLoading,
    unavailable: resolved.data ? !resolved.data.available : false,
  };
}
