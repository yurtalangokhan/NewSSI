"""Documents domain — document/chunk CRUD, upload pipeline, and search.

Owns the only Milvus connection and embedding calls in the service
(``documents.service.Collection``), the file-format parsers that turn an
upload into chunks (``documents.processor``), the async upload-job
orchestration (``documents.upload_service``), and the upload size/content
guards (``documents.upload_limits``). Depends on the ``collections`` domain
for collection metadata resolution.
"""
