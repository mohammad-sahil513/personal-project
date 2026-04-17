import os

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from dotenv import load_dotenv
load_dotenv()
# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "sdlc_knowledge_index")
SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")

# IMPORTANT:
# Set this to match your real embedding deployment.
# Examples:
# - text-embedding-ada-002  -> 1536
# - text-embedding-3-small  -> up to 1536
# - text-embedding-3-large  -> up to 3072
EMBEDDING_DIMENSIONS = 1536

# -------------------------------------------------------------------
# Credential
# -------------------------------------------------------------------

if SEARCH_API_KEY:
    credential = AzureKeyCredential(SEARCH_API_KEY)
else:
    credential = DefaultAzureCredential()

client = SearchIndexClient(
    endpoint=SEARCH_ENDPOINT,
    credential=credential,
)

# -------------------------------------------------------------------
# Vector search configuration
# -------------------------------------------------------------------

vector_search = VectorSearch(
    algorithms=[
        HnswAlgorithmConfiguration(name="hnsw-config"),
    ],
    profiles=[
        VectorSearchProfile(
            name="vector-profile",
            algorithm_configuration_name="hnsw-config",
        ),
    ],
)

# -------------------------------------------------------------------
# Ingestion-aligned schema
# -------------------------------------------------------------------

fields = [
    SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True, filterable=True),
    SimpleField(name="document_id", type=SearchFieldDataType.String, filterable=True),
    SimpleField(name="section_id", type=SearchFieldDataType.String, filterable=True),
    SimpleField(name="document_type", type=SearchFieldDataType.String, filterable=True),
    SimpleField(name="section_type", type=SearchFieldDataType.String, filterable=True),

    SearchableField(name="content", type=SearchFieldDataType.String),
    SearchableField(name="summary", type=SearchFieldDataType.String),

    SearchField(
        name="embedding",
        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
        searchable=True,
        vector_search_dimensions=EMBEDDING_DIMENSIONS,
        vector_search_profile_name="vector-profile",
    ),

    SimpleField(name="chunk_index_in_section", type=SearchFieldDataType.Int32, sortable=True),
    SimpleField(name="has_table", type=SearchFieldDataType.Boolean, filterable=True),
    SimpleField(name="has_vision_extraction", type=SearchFieldDataType.Boolean, filterable=True),
    SimpleField(name="has_list", type=SearchFieldDataType.Boolean, filterable=True),
    SimpleField(name="has_requirement_id", type=SearchFieldDataType.Boolean, filterable=True),

    SearchField(
        name="requirement_ids",
        type=SearchFieldDataType.Collection(SearchFieldDataType.String),
        searchable=False,
        filterable=False,  # you can enable later if your service/schema setup supports it
    ),
]

index = SearchIndex(
    name=INDEX_NAME,
    fields=fields,
    vector_search=vector_search,
)

created = client.create_or_update_index(index)
print(f"Created/updated index: {created.name}")