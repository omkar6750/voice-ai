"""Collapse the two historical classifier tools into classify_lead."""

import sqlalchemy as sa
from alembic import op

revision = "0023_collapse_classifier_tools"
down_revision = "0022_tool_media_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # These are the publication and version immutability guards from 0003. This
    # migration is the reviewed, explicit exception for historical published data.
    for table, trigger in (
        ("agent_versions", "validate_publication"),
        ("agent_versions", "guard_published"),
        ("tool_versions", "guard_published"),
        ("agent_version_tools", "guard_binding"),
    ):
        bind.execute(sa.text(f"ALTER TABLE public.{table} DISABLE TRIGGER {trigger}"))

    canonical_count = bind.scalar(sa.text("SELECT count(*) FROM tools WHERE name = 'classify_lead'"))
    legacy_count = bind.scalar(
        sa.text("SELECT count(*) FROM tools WHERE name IN ('classify_jev', 'classify_llm')")
    )
    if not canonical_count and not legacy_count:
        for table, trigger in (
            ("agent_versions", "validate_publication"),
            ("agent_versions", "guard_published"),
            ("tool_versions", "guard_published"),
            ("agent_version_tools", "guard_binding"),
        ):
            bind.execute(sa.text(f"ALTER TABLE public.{table} ENABLE TRIGGER {trigger}"))
        return

    bind.execute(
        sa.text(
            """
            DO $$
            DECLARE
                canonical_tool_count integer;
                published_version_count integer;
                promoted_tool_id text;
            BEGIN
                SELECT count(*) INTO canonical_tool_count
                FROM tools WHERE name = 'classify_lead';
                IF canonical_tool_count = 0 THEN
                    -- Development databases created before the canonical alias
                    -- existed contain both legacy definitions. Their schemas are
                    -- equivalent; promote the stable Jev-era identity so its
                    -- published version and evidence lineage survive.
                    SELECT id INTO promoted_tool_id
                    FROM tools
                    WHERE name IN ('classify_jev', 'classify_llm')
                    ORDER BY CASE name WHEN 'classify_jev' THEN 0 ELSE 1 END
                    LIMIT 1;
                    IF promoted_tool_id IS NULL THEN
                        RAISE EXCEPTION 'No canonical or legacy classifier tool exists';
                    END IF;
                    UPDATE tools SET name = 'classify_lead' WHERE id = promoted_tool_id;
                    UPDATE tool_versions
                    SET config = jsonb_set(
                        jsonb_set(
                            jsonb_set(config, '{name}', to_jsonb('classify_lead'::text)),
                            '{handler}', to_jsonb('classify_lead'::text)
                        ),
                        '{description}', to_jsonb('Classify the live lead using the classifier backend configured for this agent.'::text)
                    )
                    WHERE tool_id = promoted_tool_id;
                    canonical_tool_count := 1;
                END IF;
                IF canonical_tool_count <> 1 THEN
                    RAISE EXCEPTION 'Expected exactly one canonical classify_lead tool, found %', canonical_tool_count;
                END IF;
                UPDATE tool_versions
                SET config = jsonb_set(
                    jsonb_set(
                        jsonb_set(config, '{name}', to_jsonb('classify_lead'::text)),
                        '{handler}', to_jsonb('classify_lead'::text)
                    ),
                    '{description}', to_jsonb('Classify the live lead using the classifier backend configured for this agent.'::text)
                )
                WHERE tool_id = (SELECT id FROM tools WHERE name = 'classify_lead');
                SELECT count(*) INTO published_version_count
                FROM tool_versions tv
                JOIN tools t ON t.id = tv.tool_id
                WHERE t.name = 'classify_lead' AND tv.status = 'published';
                IF published_version_count = 0 THEN
                    RAISE EXCEPTION 'classify_lead must have a published version before cleanup';
                END IF;
            END $$;
            """
        )
    )

    bind.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION _collapse_classifier_json(input jsonb, old_names text[])
            RETURNS jsonb LANGUAGE plpgsql AS $$
            DECLARE
                result jsonb;
                key text;
                value jsonb;
            BEGIN
                IF input IS NULL THEN RETURN NULL; END IF;
                IF jsonb_typeof(input) = 'object' THEN
                    result := '{}'::jsonb;
                    FOR key, value IN SELECT * FROM jsonb_each(input) LOOP
                        result := result || jsonb_build_object(
                            CASE WHEN key = ANY(old_names) THEN 'classify_lead' ELSE key END,
                            _collapse_classifier_json(value, old_names)
                        );
                    END LOOP;
                    RETURN result;
                ELSIF jsonb_typeof(input) = 'array' THEN
                    SELECT COALESCE(jsonb_agg(_collapse_classifier_json(item.element, old_names)), '[]'::jsonb)
                    INTO result FROM jsonb_array_elements(input) AS item(element);
                    RETURN result;
                ELSIF jsonb_typeof(input) = 'string' AND input #>> '{}' = ANY(old_names) THEN
                    RETURN to_jsonb('classify_lead'::text);
                END IF;
                RETURN input;
            END $$;
            """
        )
    )

    # Rewrite each agent with its own historical aliases, not only the two
    # canonical names. This handles binding keys such as "lead_classifier".
    bind.execute(
        sa.text(
            """
            DO $$
            DECLARE
                row record;
                names text[];
                canonical_version_id text;
            BEGIN
                SELECT tv.id INTO canonical_version_id
                FROM tool_versions tv
                JOIN tools t ON t.id = tv.tool_id
                WHERE t.name = 'classify_lead' AND tv.status = 'published'
                ORDER BY tv.version DESC, tv.revision DESC
                LIMIT 1;

                FOR row IN SELECT id FROM agent_versions LOOP
                    SELECT COALESCE(array_agg(DISTINCT candidate), ARRAY['classify_jev','classify_llm']::text[])
                    INTO names
                    FROM (
                        SELECT avtool.binding_key AS candidate
                        FROM agent_version_tools avtool
                        JOIN tool_versions old_tv ON old_tv.id = avtool.tool_version_id
                        JOIN tools old_t ON old_t.id = old_tv.tool_id
                        WHERE avtool.agent_version_id = row.id
                          AND old_t.name IN ('classify_jev','classify_llm')
                        UNION ALL SELECT 'classify_jev'
                        UNION ALL SELECT 'classify_llm'
                    ) candidates;
                    UPDATE agent_versions
                    SET config = _collapse_classifier_json(config, names)
                    WHERE id = row.id;
                END LOOP;

                -- Collapse multiple old aliases for one agent before changing
                -- their primary keys to the single canonical binding.
                WITH ranked AS (
                    SELECT avtool.ctid,
                           row_number() OVER (
                               PARTITION BY avtool.agent_version_id
                               ORDER BY avtool.binding_key, avtool.tool_version_id
                           ) AS position
                    FROM agent_version_tools avtool
                    JOIN tool_versions old_tv ON old_tv.id = avtool.tool_version_id
                    JOIN tools old_t ON old_t.id = old_tv.tool_id
                    WHERE old_t.name IN ('classify_jev','classify_llm')
                )
                DELETE FROM agent_version_tools target
                USING ranked
                WHERE target.ctid = ranked.ctid AND ranked.position > 1;

                -- Remove an old alias when a canonical row already exists.
                DELETE FROM agent_version_tools old_binding
                WHERE old_binding.binding_key <> 'classify_lead'
                  AND EXISTS (
                      SELECT 1 FROM agent_version_tools canonical_binding
                      WHERE canonical_binding.agent_version_id = old_binding.agent_version_id
                        AND canonical_binding.binding_key = 'classify_lead'
                  )
                  AND EXISTS (
                      SELECT 1 FROM tool_versions tv JOIN tools t ON t.id = tv.tool_id
                      WHERE tv.id = old_binding.tool_version_id
                        AND t.name IN ('classify_jev','classify_llm')
                  );

                UPDATE agent_version_tools binding
                SET binding_key = 'classify_lead', tool_version_id = canonical_version_id
                WHERE binding_key IN ('classify_jev','classify_llm')
                   OR tool_version_id IN (
                       SELECT tv.id FROM tool_versions tv JOIN tools t ON t.id = tv.tool_id
                       WHERE t.name IN ('classify_jev','classify_llm')
                   );

                UPDATE agent_version_tools
                SET tool_version_id = canonical_version_id
                WHERE binding_key = 'classify_lead';
            END $$;
            """
        )
    )

    # Evidence remains readable through binding_key/result; only the deleted FK
    # target is removed.
    bind.execute(
        sa.text(
            """
            UPDATE tool_invocations invocation
            SET tool_version_id = NULL
            WHERE tool_version_id IN (
                SELECT tv.id FROM tool_versions tv JOIN tools t ON t.id = tv.tool_id
                WHERE t.name IN ('classify_jev','classify_llm')
            )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            DELETE FROM tool_versions
            WHERE tool_id IN (SELECT id FROM tools WHERE name IN ('classify_jev','classify_llm'))
            """
        )
    )
    bind.execute(sa.text("DELETE FROM tools WHERE name IN ('classify_jev','classify_llm')"))

    bind.execute(
        sa.text(
            """
            DO $$
            DECLARE remaining integer;
            BEGIN
                SELECT count(*) INTO remaining FROM tools WHERE name = 'classify_lead';
                IF remaining <> 1 THEN
                    RAISE EXCEPTION 'Classifier cleanup invariant failed: classify_lead count=%', remaining;
                END IF;
            END $$;
            """
        )
    )

    bind.execute(sa.text("DROP FUNCTION _collapse_classifier_json(jsonb, text[])"))
    for table, trigger in (
        ("agent_versions", "validate_publication"),
        ("agent_versions", "guard_published"),
        ("tool_versions", "guard_published"),
        ("agent_version_tools", "guard_binding"),
    ):
        bind.execute(sa.text(f"ALTER TABLE public.{table} ENABLE TRIGGER {trigger}"))


def downgrade() -> None:
    raise RuntimeError("Classifier tool collapse is destructive and cannot be downgraded")
