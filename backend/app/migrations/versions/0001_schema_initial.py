"""schema initial : etat atteint par la reprise historique d'avant Alembic

Revision ID: 0001
Revises: 
Create Date: 2026-11-12 21:37:08.436768
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('companies',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('legal_name', sa.String(length=160), nullable=False),
    sa.Column('sector', sa.String(length=80), nullable=False),
    sa.Column('siret', sa.String(length=20), nullable=False),
    sa.Column('address', sa.String(length=240), nullable=False),
    sa.Column('primary_color', sa.String(length=7), nullable=False),
    sa.Column('accent_color', sa.String(length=7), nullable=False),
    sa.Column('tone', sa.String(length=40), nullable=False),
    sa.Column('dpo_email', sa.String(length=160), nullable=False),
    sa.Column('logo', sa.Text(), nullable=False),
    sa.Column('brand', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('templates',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('company_id', sa.String(length=36), nullable=False),
    sa.Column('source_key', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=140), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('fields', sa.JSON(), nullable=False),
    sa.Column('design', sa.JSON(), nullable=False),
    sa.Column('thank_you', sa.JSON(), nullable=False),
    sa.Column('uses', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('company_id', 'source_key', name='uq_template_company_source')
    )
    with op.batch_alter_table('templates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_templates_company_id'), ['company_id'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('company_id', sa.String(length=36), nullable=False),
    sa.Column('email', sa.String(length=160), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=256), nullable=False),
    sa.Column('role', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    op.create_table('campaigns',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('company_id', sa.String(length=36), nullable=False),
    sa.Column('creator_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=140), nullable=False),
    sa.Column('client', sa.String(length=140), nullable=False),
    sa.Column('objective', sa.Text(), nullable=False),
    sa.Column('starts_on', sa.Date(), nullable=True),
    sa.Column('ends_on', sa.Date(), nullable=True),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_campaigns_company_id'), ['company_id'], unique=False)

    op.create_table('forms',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('campaign_id', sa.String(length=36), nullable=False),
    sa.Column('creator_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=140), nullable=False),
    sa.Column('slug', sa.String(length=160), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('visibility', sa.String(length=30), nullable=False),
    sa.Column('fields', sa.JSON(), nullable=False),
    sa.Column('design', sa.JSON(), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.Column('thank_you', sa.JSON(), nullable=False),
    sa.Column('draft', sa.JSON(), nullable=True),
    sa.Column('brief', sa.JSON(), nullable=False),
    sa.Column('identity', sa.JSON(), nullable=True),
    sa.Column('visits', sa.Integer(), nullable=False),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ),
    sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('forms', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_forms_campaign_id'), ['campaign_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_forms_slug'), ['slug'], unique=True)

    op.create_table('tunnels',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('campaign_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=140), nullable=False),
    sa.Column('slug', sa.String(length=160), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('brief', sa.JSON(), nullable=False),
    sa.Column('identity', sa.JSON(), nullable=False),
    sa.Column('goal_url', sa.String(length=2048), nullable=True),
    sa.Column('goal_label', sa.String(length=100), nullable=True),
    sa.Column('seo_title', sa.String(length=70), nullable=True),
    sa.Column('seo_description', sa.String(length=160), nullable=True),
    sa.Column('entry_page_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tunnels', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tunnels_campaign_id'), ['campaign_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tunnels_slug'), ['slug'], unique=True)

    op.create_table('form_versions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('form_id', sa.String(length=36), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('instruction', sa.Text(), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('screenshot_data_url', sa.Text(), nullable=True),
    sa.Column('images', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['form_id'], ['forms.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('form_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_form_versions_form_id'), ['form_id'], unique=False)

    op.create_table('pages',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('form_id', sa.String(length=36), nullable=True),
    sa.Column('tunnel_id', sa.String(length=36), nullable=True),
    sa.Column('name', sa.String(length=140), nullable=True),
    sa.Column('slug', sa.String(length=160), nullable=True),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('next_page_id', sa.String(length=36), nullable=True),
    sa.Column('next_page_url', sa.String(length=2048), nullable=True),
    sa.Column('html', sa.Text(), nullable=False),
    sa.Column('draft_html', sa.Text(), nullable=True),
    sa.Column('manifest', sa.JSON(), nullable=False),
    sa.Column('draft_manifest', sa.JSON(), nullable=True),
    sa.Column('settings', sa.JSON(), nullable=True),
    sa.Column('visits', sa.Integer(), nullable=False),
    sa.Column('conversions', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['form_id'], ['forms.id'], ),
    sa.ForeignKeyConstraint(['next_page_id'], ['pages.id'], ),
    sa.ForeignKeyConstraint(['tunnel_id'], ['tunnels.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('form_id', 'role', name='uq_pages_form_role'),
    sa.UniqueConstraint('slug')
    )
    with op.batch_alter_table('pages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pages_form_id'), ['form_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pages_tunnel_id'), ['tunnel_id'], unique=False)

    # Cle circulaire tunnels <-> pages : ajoutee apres la creation de `pages`.
    with op.batch_alter_table('tunnels', schema=None) as batch_op:
        batch_op.create_foreign_key('tunnels_entry_page_id_fkey', 'pages', ['entry_page_id'], ['id'])

    op.create_table('responses',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('form_id', sa.String(length=36), nullable=False),
    sa.Column('answers', sa.JSON(), nullable=False),
    sa.Column('source', sa.String(length=40), nullable=False),
    sa.Column('promo_code', sa.String(length=60), nullable=False),
    sa.Column('consent', sa.Boolean(), nullable=False),
    sa.Column('consent_text', sa.Text(), nullable=False),
    sa.Column('ip_address', sa.String(length=64), nullable=False),
    sa.Column('user_agent', sa.String(length=300), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['form_id'], ['forms.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('responses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_responses_form_id'), ['form_id'], unique=False)

    op.create_table('page_variants',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('page_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('html', sa.Text(), nullable=False),
    sa.Column('draft_html', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('page_variants', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_page_variants_page_id'), ['page_id'], unique=False)

    op.create_table('page_versions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('page_id', sa.String(length=36), nullable=False),
    sa.Column('html', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('page_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_page_versions_page_id'), ['page_id'], unique=False)

    op.create_table('tunnel_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('tunnel_id', sa.String(length=36), nullable=False),
    sa.Column('page_id', sa.String(length=36), nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=False),
    sa.Column('event_key', sa.String(length=160), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('variant_id', sa.String(length=36), nullable=False),
    sa.Column('source', sa.String(length=80), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ),
    sa.ForeignKeyConstraint(['tunnel_id'], ['tunnels.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_key', name='uq_tunnel_event_key')
    )
    with op.batch_alter_table('tunnel_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tunnel_events_page_id'), ['page_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tunnel_events_session_id'), ['session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tunnel_events_tunnel_id'), ['tunnel_id'], unique=False)



def downgrade():
    with op.batch_alter_table('tunnel_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tunnel_events_tunnel_id'))
        batch_op.drop_index(batch_op.f('ix_tunnel_events_session_id'))
        batch_op.drop_index(batch_op.f('ix_tunnel_events_page_id'))

    op.drop_table('tunnel_events')
    with op.batch_alter_table('page_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_page_versions_page_id'))

    op.drop_table('page_versions')
    with op.batch_alter_table('page_variants', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_page_variants_page_id'))

    op.drop_table('page_variants')
    with op.batch_alter_table('responses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_responses_form_id'))

    op.drop_table('responses')
    with op.batch_alter_table('tunnels', schema=None) as batch_op:
        batch_op.drop_constraint('tunnels_entry_page_id_fkey', type_='foreignkey')

    with op.batch_alter_table('pages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pages_tunnel_id'))
        batch_op.drop_index(batch_op.f('ix_pages_form_id'))

    op.drop_table('pages')
    with op.batch_alter_table('form_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_form_versions_form_id'))

    op.drop_table('form_versions')
    with op.batch_alter_table('tunnels', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tunnels_slug'))
        batch_op.drop_index(batch_op.f('ix_tunnels_campaign_id'))

    op.drop_table('tunnels')
    with op.batch_alter_table('forms', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_forms_slug'))
        batch_op.drop_index(batch_op.f('ix_forms_campaign_id'))

    op.drop_table('forms')
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_campaigns_company_id'))

    op.drop_table('campaigns')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
    with op.batch_alter_table('templates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_templates_company_id'))

    op.drop_table('templates')
    op.drop_table('companies')
