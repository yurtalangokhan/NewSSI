"""Building blocks shared by several connectors.

* :mod:`.declarative`      - ``DeclarativeRestSource``, ``StreamSpec`` and the paginator strategies
* :mod:`.rest_source`      - ``RestSource``: httpx client lifecycle, retry, JSON helpers
* :mod:`.graphql`          - ``GraphQLSource``: query execution and Relay connection paging
* :mod:`.folder_tree`      - ``FolderTreeSource``: breadth-first walk for stores without recursion
* :mod:`.microsoft_graph`  - ``GraphSource``: Entra ID client-credentials auth + OData paging
* :mod:`.google_auth`      - ``GoogleSource``: service-account JWT / access-token auth
* :mod:`.oauth2`           - cached OAuth2 tokens for server-to-server flows
* :mod:`.s3_connection`    - AWS / MinIO / GCS / OCI / R2 settings and the boto3 client factory
* :mod:`.atlassian_auth`   - basic / bearer auth headers for Confluence, Jira and Bitbucket
* :mod:`.file_system`      - ``FileSystemSource``: one reader for FTP / SFTP / SMB / local trees
* :mod:`.file_formats`     - csv / jsonl / json / text record parsing for file-based sources
* :mod:`.cursor`           - ``CursorTracker``: incremental cursors, one comparator, checkpoints
* :mod:`.tabular`          - SQL sources: table streams, identifier quoting, values to JSON and back
* :mod:`.blocking`         - ``iterate_in_thread``: drain a blocking iterator off the event loop
* :mod:`.json_schema`      - JSON Schema type inference from sample records
* :mod:`.text`             - HTML to plain text

Nothing here is a connector; concrete sources and destinations live in
``connector.sources`` and ``connector.destinations``.
"""
