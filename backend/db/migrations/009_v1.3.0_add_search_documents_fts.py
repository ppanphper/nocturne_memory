import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def up(engine: AsyncEngine):
    """
    Version: v1.3.0
    Add derived full-text search documents and backfill them from live graph data.
    """
    is_postgres = "postgresql" in str(engine.url)
    false_val = "FALSE" if is_postgres else "0"
    search_text_expr = (
        "coalesce(path, '') || ' ' || "
        "coalesce(uri, '') || ' ' || "
        "coalesce(content, '') || ' ' || "
        "coalesce(disclosure, '') || ' ' || "
        "coalesce(keywords_text, '')"
    )
    keyword_agg = (
        "COALESCE((SELECT string_agg(keyword, ' ') FROM glossary_keywords g "
        "WHERE g.node_uuid = e.child_uuid), '')"
        if is_postgres
        else "COALESCE((SELECT group_concat(keyword, ' ') FROM glossary_keywords g "
        "WHERE g.node_uuid = e.child_uuid), '')"
    )

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS search_documents (
                    domain VARCHAR(64) NOT NULL,
                    path VARCHAR(512) NOT NULL,
                    node_uuid VARCHAR(36) NOT NULL REFERENCES nodes(uuid) ON DELETE CASCADE,
                    memory_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    uri TEXT NOT NULL,
                    content TEXT NOT NULL,
                    disclosure TEXT,
                    keywords_text TEXT NOT NULL DEFAULT '',
                    priority INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (domain, path)
                )
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_search_documents_node_uuid "
                "ON search_documents(node_uuid)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_search_documents_memory_id "
                "ON search_documents(memory_id)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_search_documents_domain "
                "ON search_documents(domain)"
            )
        )

        if is_postgres:
            await conn.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_search_documents_fts
                    ON search_documents
                    USING GIN (
                        to_tsvector('simple', {search_text_expr})
                    )
                    """
                )
            )
        else:
            await conn.execute(
                text(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS search_documents_fts
                    USING fts5(
                        domain UNINDEXED,
                        path,
                        node_uuid UNINDEXED,
                        uri,
                        content,
                        disclosure,
                        keywords_text,
                        tokenize = 'unicode61'
                    )
                    """
                )
            )

        await conn.execute(text("DELETE FROM search_documents"))
        if not is_postgres:
            await conn.execute(text("DELETE FROM search_documents_fts"))

        await conn.execute(
            text(
                f"""
                INSERT INTO search_documents (
                    domain,
                    path,
                    node_uuid,
                    memory_id,
                    uri,
                    content,
                    disclosure,
                    keywords_text,
                    priority
                )
                SELECT
                    p.domain,
                    p.path,
                    e.child_uuid,
                    m.id,
                    p.domain || '://' || p.path,
                    m.content,
                    e.disclosure,
                    {keyword_agg},
                    e.priority
                FROM paths p
                JOIN edges e ON p.edge_id = e.id
                JOIN memories m
                  ON m.node_uuid = e.child_uuid
                 AND m.deprecated = {false_val}
                """
            )
        )

        if not is_postgres:
            await conn.execute(
                text(
                    """
                    INSERT INTO search_documents_fts (
                        domain,
                        path,
                        node_uuid,
                        uri,
                        content,
                        disclosure,
                        keywords_text
                    )
                    SELECT
                        domain,
                        path,
                        node_uuid,
                        uri,
                        content,
                        coalesce(disclosure, ''),
                        keywords_text
                    FROM search_documents
                    """
                )
            )

    logger.info("Migration 009: created and backfilled search_documents FTS index")
