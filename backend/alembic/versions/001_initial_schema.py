"""Initial schema for legislative redline tool

Revision ID: 001
Revises:
Create Date: 2025-01-08

Creates tables for:
- documents: Uploaded documents with proposed amendments
- statutes: Cached current law from govinfo.gov and eCFR.gov
- citations: USC/CFR/PubLaw citations detected in documents
- comparisons: Generated redline comparisons
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ENUM


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


# Define enum types
documentstatus_enum = ENUM('uploaded', 'parsing', 'parsed', 'processing', 'completed', 'failed', name='documentstatus', create_type=False)
citationtype_enum = ENUM('usc', 'cfr', 'publaw', name='citationtype', create_type=False)
statutesource_enum = ENUM('govinfo', 'ecfr', 'manual', name='statutesource', create_type=False)
amendmenttype_enum = ENUM('strike_insert', 'insert_after', 'read_as_follows', 'add_at_end', 'strike', 'unknown', name='amendmenttype', create_type=False)


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE documentstatus AS ENUM ('uploaded', 'parsing', 'parsed', 'processing', 'completed', 'failed')")
    op.execute("CREATE TYPE citationtype AS ENUM ('usc', 'cfr', 'publaw')")
    op.execute("CREATE TYPE statutesource AS ENUM ('govinfo', 'ecfr', 'manual')")
    op.execute("CREATE TYPE amendmenttype AS ENUM ('strike_insert', 'insert_after', 'read_as_follows', 'add_at_end', 'strike', 'unknown')")

    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_type', sa.String(10), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('raw_text', sa.Text, nullable=True),
        sa.Column('status', documentstatus_enum, nullable=False, server_default='uploaded'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime, nullable=False, server_default=sa.text("NOW() + INTERVAL '24 hours'")),
    )

    # Create statutes table (before citations since citations reference it)
    op.create_table(
        'statutes',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('citation_type', sa.String(10), nullable=False),
        sa.Column('title', sa.Integer, nullable=False),
        sa.Column('section', sa.String(50), nullable=False),
        sa.Column('full_text', sa.Text, nullable=False),
        sa.Column('heading', sa.String(500), nullable=True),
        sa.Column('source', statutesource_enum, nullable=False),
        sa.Column('source_url', sa.String(500), nullable=True),
        sa.Column('effective_date', sa.DateTime, nullable=True),
        sa.Column('fetched_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime, nullable=False, server_default=sa.text("NOW() + INTERVAL '7 days'")),
        sa.UniqueConstraint('citation_type', 'title', 'section', name='uq_statute_citation'),
    )

    # Create citations table
    op.create_table(
        'citations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('citation_type', citationtype_enum, nullable=False),
        sa.Column('title', sa.Integer, nullable=True),
        sa.Column('section', sa.String(50), nullable=False),
        sa.Column('subsection', sa.String(100), nullable=True),
        sa.Column('raw_text', sa.String(255), nullable=False),
        sa.Column('position_start', sa.Integer, nullable=True),
        sa.Column('position_end', sa.Integer, nullable=True),
        sa.Column('context_text', sa.Text, nullable=True),
        sa.Column('statute_fetched', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('statute_id', UUID(as_uuid=True), sa.ForeignKey('statutes.id'), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
    )

    # Add index on document_id for faster lookups
    op.create_index('ix_citations_document_id', 'citations', ['document_id'])

    # Create comparisons table
    op.create_table(
        'comparisons',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('citation_id', UUID(as_uuid=True), sa.ForeignKey('citations.id'), nullable=True),
        sa.Column('citation_text', sa.String(255), nullable=True),
        sa.Column('amendment_type', amendmenttype_enum, nullable=True),
        sa.Column('amendment_instruction', sa.Text, nullable=True),
        sa.Column('original_text', sa.Text, nullable=True),
        sa.Column('amended_text', sa.Text, nullable=True),
        sa.Column('diff_html', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
    )

    # Add index on document_id for faster lookups
    op.create_index('ix_comparisons_document_id', 'comparisons', ['document_id'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('ix_comparisons_document_id', table_name='comparisons')
    op.drop_table('comparisons')

    op.drop_index('ix_citations_document_id', table_name='citations')
    op.drop_table('citations')

    op.drop_table('statutes')
    op.drop_table('documents')

    # Drop enum types
    op.execute('DROP TYPE amendmenttype')
    op.execute('DROP TYPE statutesource')
    op.execute('DROP TYPE citationtype')
    op.execute('DROP TYPE documentstatus')
