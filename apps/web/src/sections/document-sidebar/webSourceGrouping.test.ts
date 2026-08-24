import {
  isAllWebSources,
  groupSourcesByDomain,
  splitMessageSources,
} from "./webSourceGrouping";
import { OnyxDocument } from "@/lib/search/interfaces";
import { ValidSources } from "@/lib/types";
import { Packet, PacketType } from "@/app/app/services/streamingModels";

const webDoc = (id: string, link: string): OnyxDocument =>
  ({
    document_id: id,
    semantic_identifier: id,
    link,
    source_type: ValidSources.Web,
    blurb: "",
    boost: 0,
    hidden: false,
    score: 1,
    chunk_ind: 0,
    match_highlights: [],
    metadata: {},
    updated_at: null,
    is_internet: true,
  }) as OnyxDocument;

const internalDoc = (id: string): OnyxDocument =>
  ({
    document_id: id,
    semantic_identifier: id,
    link: "",
    source_type: ValidSources.GoogleDrive,
    blurb: "",
    boost: 0,
    hidden: false,
    score: 1,
    chunk_ind: 0,
    match_highlights: [],
    metadata: {},
    updated_at: null,
    is_internet: false,
  }) as OnyxDocument;

const createPacket = (type: string, data: Record<string, any> = {}): Packet =>
  ({
    placement: { turn_index: 0, tab_index: 0 },
    obj: { type, ...data },
  }) as Packet;

describe("isAllWebSources", () => {
  test("false for an empty list", () => {
    expect(isAllWebSources([])).toBe(false);
  });

  test("true when every document is a web result", () => {
    expect(
      isAllWebSources([
        webDoc("1", "https://onyx.app"),
        webDoc("2", "https://docs.onyx.app"),
      ])
    ).toBe(true);
  });

  test("false when any document is an internal source", () => {
    expect(
      isAllWebSources([webDoc("1", "https://onyx.app"), internalDoc("2")])
    ).toBe(false);
  });
});

describe("groupSourcesByDomain", () => {
  test("groups documents sharing a hostname, preserving first-seen order", () => {
    const docs = [
      webDoc("1", "https://onyx.app/page-a"),
      webDoc("2", "https://docs.onyx.app"),
      webDoc("3", "https://onyx.app/page-b"),
    ];

    const groups = groupSourcesByDomain(docs);

    expect(groups.map((g) => g.domain)).toEqual(["onyx.app", "docs.onyx.app"]);
    expect(groups[0]?.documents.map((d) => d.document_id)).toEqual(["1", "3"]);
    expect(groups[1]?.documents.map((d) => d.document_id)).toEqual(["2"]);
  });

  test("a single document still gets its own one-element group", () => {
    const groups = groupSourcesByDomain([webDoc("1", "https://onyx.app")]);

    expect(groups).toEqual([
      {
        domain: "onyx.app",
        documents: [expect.objectContaining({ document_id: "1" })],
      },
    ]);
  });

  test("an unparseable link falls back to an empty-string domain group", () => {
    const groups = groupSourcesByDomain([webDoc("1", "not-a-url")]);

    expect(groups[0]?.domain).toBe("");
  });

  test("empty input returns an empty list", () => {
    expect(groupSourcesByDomain([])).toEqual([]);
  });
});

describe("splitMessageSources", () => {
  test("separates read documents from search documents and deduplicates", () => {
    const doc1 = webDoc("https://valkey.io", "https://valkey.io");
    const doc2 = webDoc("https://redis.io", "https://redis.io");
    const doc3 = webDoc(
      "https://github.com/valkey-io/valkey",
      "https://github.com/valkey-io/valkey"
    );

    const packets: Packet[] = [
      createPacket(PacketType.SEARCH_TOOL_DOCUMENTS_DELTA, {
        documents: [doc1, doc2, doc3],
      }),
      createPacket(PacketType.FETCH_TOOL_DOCUMENTS, {
        documents: [doc1],
      }),
    ];

    const result = splitMessageSources(packets);

    expect(result.readDocuments).toHaveLength(1);
    expect(result.readDocuments[0]?.document_id).toBe("https://valkey.io");

    // doc1 was read, so it must not duplicate in searchDocuments
    expect(result.searchDocuments).toHaveLength(2);
    expect(result.searchDocuments.map((d) => d.document_id)).toEqual([
      "https://redis.io",
      "https://github.com/valkey-io/valkey",
    ]);
  });

  test("extracts internal documents from persisted documents", () => {
    const intDoc = internalDoc("doc-internal-1");
    const persistedWebDoc = webDoc("web-doc-1", "https://example.com");

    const result = splitMessageSources([], [intDoc, persistedWebDoc]);

    expect(result.internalDocuments).toEqual([intDoc]);
    expect(result.readDocuments).toEqual([]);
    expect(result.searchDocuments).toEqual([]);
  });
});
