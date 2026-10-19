"""Immutable knowledge releases. Publish a new collection, never mutate live policy."""

import os
from qdrant_client.http import models
from src.common.embed_factory import COHERE_MODEL, LOCAL_MODEL, use_cohere_embeddings


def knowledge_alias():
    return os.getenv("KNOWLEDGE_ALIAS", "flipkart_faqs_live")


def embedding_identity():
    return COHERE_MODEL if use_cohere_embeddings() else LOCAL_MODEL


def publish(client, collection, alias=None):
    alias = alias or knowledge_alias()
    existing = {item.alias_name for item in client.get_aliases().aliases}
    if alias not in existing and client.collection_exists(alias):
        raise ValueError(
            "Alias collides with a legacy collection; choose a new KNOWLEDGE_ALIAS without deleting live data"
        )
    operations = []
    if alias in existing:
        operations.append(
            models.DeleteAliasOperation(
                delete_alias=models.DeleteAlias(alias_name=alias)
            )
        )
    operations.append(
        models.CreateAliasOperation(
            create_alias=models.CreateAlias(
                alias_name=alias, collection_name=collection
            )
        )
    )
    client.update_collection_aliases(change_aliases_operations=operations)
