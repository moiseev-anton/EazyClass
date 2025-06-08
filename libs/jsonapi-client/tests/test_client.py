from unittest.mock import Mock
from urllib.parse import urlparse
from yarl import URL

from aiohttp import ClientResponse
from aiohttp.helpers import TimerNoop
import jsonschema
import pytest
from requests import Response
import json
import os
from jsonschema import ValidationError
from jsonapi_client import ResourceTuple
import jsonapi_client.objects
import jsonapi_client.relationships
import jsonapi_client.resourceobject
from jsonapi_client.exceptions import DocumentError, AsyncError
from jsonapi_client.filter import Filter
from jsonapi_client.session import Session
from unittest import mock


external_references = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'properties': {
        'referenceId': {'type': ['string', 'null']},
        'referenceType': {'type': ['string', 'null']},
        'target': {
            'relation': 'to-one',
            'resource': ['individuals', 'products']
        },
        'validFor': {
            'properties': {
                'endDatetime': {'format': 'date-time', 'type': ['string', 'null']},
                'startDatetime': {'format': 'date-time', 'type': ['string', 'null']}
            },
            'required': ['startDatetime'],
            'type': 'object'
        },
        'nullField': {
            'properties': {
                'uselessField': {'type': ['string', 'null']}
            },
            'type': 'object'
        }
    },
    'type': 'object'
}

leases = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'properties': {
        'leaseItems': {'relation': 'to-many', 'resource': ['leaseItems']},
        'userAccount': {'relation': 'to-one', 'resource': ['userAccounts']},
        'leaseId': {'type': ['string', 'null']},
        'externalReferences': {'relation': 'to-many', 'resource': ['externalReferences']},
        'activeStatus': {'enum': ['pending', 'active', 'terminated']},
        'parentLease': {'relation': 'to-one', 'resource': ['salesLeases']},
        'referenceNumber': {'type': ['string', 'null']},
        'relatedParties': {'relation': 'to-many', 'resource': ['partyRelationships']},
        'validFor': {
            'properties': {
                'endDatetime': {'format': 'date-time', 'type': ['string', 'null']},
                'startDatetime': {'format': 'date-time', 'type': ['string', 'null']}
            },
            'required': ['startDatetime'],
            'type': 'object'
        }
    },
    'type': 'object'
}

user_accounts = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'properties': {
        'accountId': {'type': ['string', 'null']},
        'userType': {'type': ['string', 'null']},
        'leases': {'relation': 'to-many', 'resource': ['leases']},
        'associatedPartnerAccounts': {'relation': 'to-many', 'resource': ['partnerAccounts']},
        'partnerAccounts': {'relation': 'to-many', 'resource': ['partnerAccounts']},
        'externalReferences': {'relation': 'to-many', 'resource': ['externalReferences']},
        'activeStatus': {'enum': ['pending', 'active', 'inactive', 'suspended']},
        'name': {'type': ['string', 'null']},
        'validFor': {
            'properties': {
                'endDatetime': {'format': 'date-time', 'type': ['string', 'null']},
                'startDatetime': {'format': 'date-time', 'type': ['string', 'null']}
            },
            'required': ['startDatetime'],
            'type': 'object'
        }
    },
    'type': 'object'
}


# TODO: figure out why this is not correctly in resources-schema
leases['properties']['validFor']['properties']['meta'] = {
    'type': 'object',
    'properties': {'type': {'type': 'string'}}
}

api_schema_simple = {
    'leases': leases
}

api_schema_all = {
    'leases': leases,
    'externalReferences': external_references,
    'userAccounts': user_accounts
}


# jsonapi.org example

articles = {
    'properties': {
        'title': {'type': 'string'},
        'author': {'relation': 'to-one', 'resource': ['people']},
        'comments': {'relation': 'to-many', 'resource': ['comments']},
        'commentOrAuthor': {'relation': 'to-one', 'resource': ['comments', 'people']},
        'commentsOrAuthors': {'relation': 'to-many', 'resource': ['comments', 'people']}
    }
}

people = {
    'properties': {
        'firstName': {'type': 'string'},
        'lastName': {'type': 'string'},
        'twitter': {'type': ['null', 'string']}
    }
}

comments = {
    'properties': {
        'body': {'type': 'string'},
        'author': {'relation': 'to-one', 'resource': ['people']}
    }
}

article_schema_all = {
    'articles': articles,
    'people': people,
    'comments': comments
}

article_schema_simple = {
    'articles': articles
}

# Invitation is an examaple of a resource without any attributes
invitations = {
    'properties': {
        'host': {'relation': 'to-one', 'resource': ['people']},
        'guest': {'relation': 'to-one', 'resource': ['people']}
    }
}

invitation_schema = {
    'invitations': invitations
}


@pytest.fixture(scope='function', params=[None, article_schema_simple,
                                          article_schema_all])
def article_schema(request):
    return request.param


@pytest.fixture(scope='function', params=[None, api_schema_simple, api_schema_all])
def api_schema(request):
    return request.param


def load(filename):
    filename = filename.replace('?', '__').replace('"', '__')
    fname = os.path.join(os.path.dirname(__file__), 'json', f'{filename}.json')
    try:
        with open(fname, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise DocumentError(f'File not found: {fname}', errors=dict(status_code=404))


#mock_fetch_cm = async_mock.patch('jsonapi_client.session.fetch_json', new_callable=MockedFetch)


@pytest.fixture
def mock_req_async(mocker):
    rv = (201, {}, 'location')

    class MockedReqAsync(Mock):
        async def __call__(self, *args):
            super().__call__(*args)
            return rv

    return mocker.patch('jsonapi_client.session.Session.http_request_async', new_callable=MockedReqAsync)


@pytest.fixture
def mocked_fetch(mocker):
    def mock_fetch(url):
        parsed_url = urlparse(url)
        file_path = parsed_url.path[1:]
        query = parsed_url.query
        return load(f'{file_path}?{query}' if query else file_path)

    class MockedFetchAsync:
        async def __call__(self, url):
            return mock_fetch(url)

    mocker.patch('jsonapi_client.session.Session._fetch_json_async', new_callable=MockedFetchAsync)


@pytest.fixture
def mock_update_resource(mocker):
    return mocker.patch('jsonapi_client.resourceobject.ResourceObject._update_resource')


@pytest.fixture
def session():
    return mock.Mock()


@pytest.mark.asyncio
async def test_initialization_async(mocked_fetch, article_schema):
    async with Session('http://localhost:8080', schema=article_schema) as s:
        doc = await s.get('articles')
        assert s.resources_by_link['http://example.com/articles/1'] is \
               s.resources_by_resource_identifier[('articles', '1')]
        assert s.resources_by_link['http://example.com/comments/12'] is \
               s.resources_by_resource_identifier[('comments', '12')]
        assert s.resources_by_link['http://example.com/comments/5'] is \
               s.resources_by_resource_identifier[('comments', '5')]
        assert s.resources_by_link['http://example.com/people/9'] is \
               s.resources_by_resource_identifier[('people', '9')]


@pytest.mark.asyncio
async def test_resourceobject_without_attributes_async(mocked_fetch):
    async with Session('http://localhost:8080', schema=invitation_schema) as s:
        doc = await s.get('invitations')
        assert len(doc.resources) == 1
        invitation = doc.resources[0]
        assert invitation.id == "1"
        assert invitation.type == "invitations"
        assert doc.links.self.href == 'http://example.com/invitations'
        attr_set = {'host', 'guest'}

        my_attrs = {i for i in dir(invitation.fields) if not i.startswith('_')}

        assert my_attrs == attr_set


@pytest.mark.asyncio
async def test_basic_attributes_async(mocked_fetch, article_schema):
    async with Session('http://localhost:8080', schema=article_schema) as s:
        doc = await s.get('articles')
        assert len(doc.resources) == 3
        article = doc.resources[0]
        assert article.id == "1"
        assert article.type == "articles"
        assert article.title.startswith('JSON API paints')
        assert article['title'].startswith('JSON API paints')

        assert doc.links.self.href == 'http://example.com/articles'

        attr_set = {'title', 'author', 'comments', 'nested1', 'comment_or_author', 'comments_or_authors'}

        my_attrs = {i for i in dir(article.fields) if not i.startswith('_')}

        assert my_attrs == attr_set


@pytest.mark.asyncio
async def test_relationships_iterator_async(mocked_fetch, article_schema):
    async with Session('http://localhost:8080', schema=article_schema, use_relationship_iterator=True) as s:
        doc = await s.get('articles')
        article, article2, article3 = doc.resources
        comments = article.comments
        assert isinstance(comments, jsonapi_client.relationships.MultiRelationship)
        assert len(comments._resource_identifiers) == 2


@pytest.mark.asyncio
async def test_relationships_single_async(mocked_fetch, article_schema):
    async with Session('http://localhost:8080', schema=article_schema) as s:
        doc = await s.get('articles')
        article, article2, article3 = doc.resources

        author = article.author
        assert isinstance(author, jsonapi_client.relationships.SingleRelationship)
        with pytest.raises(AsyncError):
            _ = author.resource

        await author.fetch()
        author_res = author.resource
        assert {i for i in dir(author_res.fields) if not i.startswith('_')} \
               == {'first_name', 'last_name', 'twitter'}
        assert author_res.type == 'people'
        assert author_res.id == '9'

        assert author_res.first_name == 'Dan'
        assert author_res.last_name == 'Gebhardt'
        assert author.links.self.href == "http://example.com/articles/1/relationships/author"

        author = article.author.resource
        assert isinstance(author, jsonapi_client.resourceobject.ResourceObject)
        assert author.first_name == 'Dan'
        assert author.last_name == 'Gebhardt'
        assert author.links.self.href == "http://example.com/people/9"

        await article.comment_or_author.fetch()
        assert article.comment_or_author.resource.id == '12'
        assert article.comment_or_author.resource.type == 'comments'
        assert article.comment_or_author.resource.body == 'I like XML better'

        await article2.comment_or_author.fetch()
        assert article2.comment_or_author.resource.id == '9'
        assert article2.comment_or_author.resource.type == 'people'
        assert article2.comment_or_author.resource.first_name == 'Dan'

        await article3.author.fetch()
        await article3.comment_or_author.fetch()
        assert article3.author.resource is None
        assert article3.comment_or_author.resource is None


@pytest.mark.asyncio
async def test_relationships_multi_async(mocked_fetch, article_schema):
    async with Session('http://localhost:8080', schema=article_schema) as s:
        doc = await s.get('articles')
        article = doc.resource
        comments = article.comments
        assert isinstance(comments, jsonapi_client.relationships.MultiRelationship)
        assert len(comments._resource_identifiers) == 2

        c1, c2 = await comments.fetch()

        assert isinstance(c1, jsonapi_client.resourceobject.ResourceObject)
        assert 'body' in dir(c1)
        assert c1.body == "First!"

        assert isinstance(c1.author, jsonapi_client.relationships.SingleRelationship)

        assert c2.body == 'I like XML better'
        with pytest.raises(AsyncError):
            assert c2.author.resource.id == '9'
        await c2.author.fetch()
        author_res = c2.author.resource
        assert author_res.id == '9'
        assert author_res.first_name == 'Dan'
        assert author_res.last_name == 'Gebhardt'

        rel = article.comments_or_authors
        assert isinstance(rel, jsonapi_client.relationships.MultiRelationship)
        await rel.fetch()
        res1, res2 = rel.resources

        assert res1.id == '9'
        assert res1.type == 'people'
        assert res1.first_name == 'Dan'

        assert res2.id == '12'
        assert res2.type == 'comments'
        assert res2.body == 'I like XML better'


@pytest.mark.asyncio
async def test_fetch_external_resources_async(mocked_fetch, article_schema):
    async with Session('http://localhost:8080', schema=article_schema) as s:
        doc = await s.get('articles')
        article = doc.resource
        comments = article.comments
        assert isinstance(comments, jsonapi_client.relationships.MultiRelationship)
        session = article.session
        c1, c2 = await comments.fetch()
        assert c1.body == "First!"
        assert len(session.resources_by_resource_identifier) == 6
        assert len(session.resources_by_link) == 5
        assert len(session.documents_by_link) == 1

        with pytest.raises(AsyncError):
            _ = c1.author.resource.id
        await c1.author.fetch()
        # fetch external content
        c1_author = c1.author.resource
        assert c1_author.id == "2"
        assert len(session.resources_by_resource_identifier) == 7
        assert len(session.resources_by_link) == 6
        assert len(session.documents_by_link) == 2
        assert c1_author.type == "people"
        assert c1_author.first_name == 'Dan 2'
        assert c1_author.last_name == 'Gebhardt 2'


@pytest.mark.asyncio
async def test_error_404_async(mocked_fetch, api_schema):
    async with Session('http://localhost:8080/api', schema=api_schema) as s:
        documents = await s.get('leases')
        d1 = documents.resources[1]

        parent_lease = d1.parent_lease
        assert isinstance(parent_lease, jsonapi_client.relationships.LinkRelationship)
        with pytest.raises(AsyncError):
            _ = parent_lease.resource.active_status

        with pytest.raises(DocumentError) as e:
            res = await parent_lease.fetch()

        assert e.value.errors['status_code'] == 404
        with pytest.raises(DocumentError) as e:
            await s.get('error')
        assert 'Error document was fetched' in str(e.value)


@pytest.mark.asyncio
async def test_relationships_with_context_manager_async_async(mocked_fetch, api_schema):
    async with Session('http://localhost:8080/api', schema=api_schema) as s:
        documents = await s.get('leases')
        d1 = documents.resources[0]

        assert d1.lease_id is None
        assert d1.id == 'qvantel-lease1'
        assert d1.type == 'leases'
        assert d1.active_status == d1.fields.active_status == 'active'
        assert d1.valid_for.start_datetime == "2015-07-06T12:23:26.000Z"
        assert d1['validFor']['startDatetime'] == "2015-07-06T12:23:26.000Z"
        assert d1.valid_for.meta.type == 'validForDatetime'
        dird = dir(d1)
        assert 'external_references' in dird

        ext_refs = d1.external_references
        ext_ref_res = (await ext_refs.fetch())[0]

        assert ext_ref_res.reference_id == ext_ref_res.fields.reference_id == '0123015150'
        assert ext_ref_res.id == 'qvantel-lease1-extref'
        assert ext_ref_res.type == 'externalReferences'

        assert isinstance(ext_ref_res, jsonapi_client.resourceobject.ResourceObject)

        assert ext_ref_res.reference_id == '0123015150'
        assert ext_ref_res.id == 'qvantel-lease1-extref'
        assert ext_ref_res.type == 'externalReferences'

        assert 'user_account' in dird
        await d1.user_account.fetch()
        assert d1.user_account.resource.id == 'qvantel-useraccount1'
        assert d1.user_account.resource.type == 'userAccounts'
        assert d1.links.self.href == '/api/leases/qvantel-lease1'

        await d1.parent_lease.fetch()
        parent_lease = d1.parent_lease.resource
        assert parent_lease.active_status == 'active'

    assert not s.resources_by_link
    assert not s.resources_by_resource_identifier
    assert not s.documents_by_link


@pytest.mark.asyncio
async def test_more_relationships_async_fetch(mocked_fetch, api_schema):
    async with Session('http://localhost:8080/api', schema=api_schema) as s:
        documents = await s.get('leases')
        d1 = documents.resources[0]
        dird = dir(d1)

        assert 'external_references' in dird

        # Relationship collection (using link rather than ResourceObject)
        # fetches http://localhost:8080/api/leases/qvantel-lease1/external-references

        ext_ref = d1.external_references
        assert isinstance(ext_ref, jsonapi_client.relationships.LinkRelationship)

        with pytest.raises(AsyncError):
            len(ext_ref.resources) == 1

        with pytest.raises(AsyncError):
            _ = ext_ref.resources.reference_id

        ext_ref_res = (await ext_ref.fetch())[0]

        assert ext_ref_res.reference_id == '0123015150'

        assert ext_ref_res.id == 'qvantel-lease1-extref'
        assert ext_ref_res.type == 'externalReferences'

        ext_ref = d1.external_references.resources[0]
        assert isinstance(ext_ref, jsonapi_client.resourceobject.ResourceObject)

        assert ext_ref.reference_id == '0123015150'
        assert ext_ref.id == 'qvantel-lease1-extref'
        assert ext_ref.type == 'externalReferences'

        assert 'user_account' in dird
        await d1.user_account.fetch()
        assert d1.user_account.resource.id == 'qvantel-useraccount1'
        assert d1.user_account.resource.type == 'userAccounts'
        assert d1.links.self.href == '/api/leases/qvantel-lease1'

        # Single relationship (using link rather than ResourceObject)
        # Fetches http://localhost:8080/api/leases/qvantel-lease1/parent-lease
        parent_lease = d1.parent_lease
        assert isinstance(parent_lease, jsonapi_client.relationships.LinkRelationship)
        # ^ Anything is not fetched yet
        await parent_lease.fetch()
        assert parent_lease.resource.active_status == 'active'
        # ^ now parent lease is fetched, but attribute access goes through Relationship


class SuccessfullResponse:
    status_code = 200
    headers = {}
    content = ''
    @classmethod
    def json(cls):
        return {}


@pytest.mark.asyncio
async def test_patching(mocker, mocked_fetch, api_schema, mock_update_resource):
    mock_patch = mocker.patch('requests.request')
    mock_patch.return_value = SuccessfullResponse

    s = Session('http://localhost:80801/api', schema=api_schema)
    document = await s.get('leases')
    documents = document.resources

    # if single document (not collection) we must also be able to
    # set attributes of main resourceobject directly
    # TODO test this^

    assert len(documents) == 4
    with pytest.raises(AttributeError):
        documents.someattribute = 'something'

    d1 = documents[0]

    # Let's change fields in resourceobject
    assert d1.active_status == 'active'
    d1.active_status = 'terminated'
    assert d1.is_dirty
    assert s.is_dirty
    assert 'active-status' in d1.dirty_fields
    await d1.commit()  # alternatively s.commit() which does commit for all dirty objects
    assert len(d1.dirty_fields) == 0
    assert not d1.is_dirty
    assert not s.is_dirty

    assert d1.valid_for.start_datetime == "2015-07-06T12:23:26.000Z"

    d1.valid_for.start_datetime = 'something-else'
    d1.valid_for.new_field = 'something-new'
    assert d1.valid_for.is_dirty
    assert 'start-datetime' in d1.valid_for._dirty_attributes
    assert d1.is_dirty
    assert 'valid-for' in d1.dirty_fields

    assert d1._attributes.diff == {'valid-for': {'start-datetime': 'something-else',
                                                       'new-field': 'something-new'}}

    assert d1.external_references[0].id == 'qvantel-lease1-extref'

    assert len(d1.external_references) == 1

    add_resources = [ResourceTuple(str(i), 'externalReferences') for i in [1,2]]
    d1.external_references += add_resources

    assert len(d1.relationships.external_references.document.resources) == 1 # Document itself should not change
    assert len(d1.external_references) == 3

    d1.external_references += [ResourceTuple('3', 'externalReferences')]
    assert len(d1.relationships.external_references.document.resources) == 1 # Document itself should not change
    assert len(d1.external_references) == 4
    assert d1.relationships.external_references.is_dirty
    assert len(mock_patch.mock_calls) == 1
    await d1.commit()
    assert len(mock_patch.mock_calls) == 2
    actual_data = mock_patch.mock_calls[1][2]['json']['data']
    expected_data = {
        'id': 'qvantel-lease1',
        'type': 'leases',
        'attributes': {
            'validFor': {'newField': 'something-new',
                          'startDatetime': 'something-else'}},
        'relationships': {
            'externalReferences': {
                'data': [
                    {'id': 'qvantel-lease1-extref',
                     'type': 'externalReferences'},
                    {'id': '1',
                     'type': 'externalReferences'},
                    {'id': '2',
                     'type': 'externalReferences'},
                    {'id': '3',
                     'type': 'externalReferences'}
                     ]}}}
    assert actual_data == expected_data
    assert not d1.is_dirty
    assert not d1.valid_for.is_dirty
    assert not d1.relationships.external_references.is_dirty
    # After commit we receive new data from the server, and everything should be as expected again
    await s.close()


@pytest.mark.asyncio
async def test_result_pagination(mocked_fetch, api_schema):
    s = Session('http://localhost:8080/', schema=api_schema)

    agr_pages = []
    doc = await s.get('test_leases')
    agr1 = doc.resources[0]

    agr_pages.append(agr1)

    # Pagination of collection
    assert len(doc.resources) == 2  # length of received collection

    agr_next = doc.links.next.fetch()
    while agr_next:
        agr_pages.append(agr_next)
        assert len(agr_next.resources) == 2
        agr_prev = agr_next
        agr_cur = agr_next
        agr_next = await agr_next.links.next.fetch()
        if agr_next:
            assert agr_next.links.prev == agr_prev.links.self

    assert agr_cur.links.self == doc.links.last
    assert agr_cur.links.first == doc.links.self == doc.links.first

    d1 = doc.resources[0]
    ext_refs = d1.external_references

    assert len(ext_refs) == 2

    ext_refs2 = await d1.relationships.external_references.document.links.next.fetch()
    assert len(ext_refs2.resources) == 2
    assert d1.relationships.external_references.document.links.last == ext_refs2.links.self
    await s.close()


@pytest.mark.asyncio
async def test_result_pagination_iteration_async(mocked_fetch, api_schema):
    async with Session('http://localhost:8080/', schema=api_schema) as s:
        leases = [r async for r in s.iterate('test_leases')]
        assert len(leases) == 6
        for l in range(len(leases)):
            assert leases[l].id == str(l+1)


@pytest.mark.asyncio
async def test_result_filtering(mocked_fetch, api_schema):
    async with Session('http://localhost:8080/', schema=api_schema) as s:
        result = await s.get('test_leases', Filter(title='Dippadai'))
        result2 = await s.get('test_leases', Filter(f'filter[title]=Dippadai'))
        assert result == result2

        d1 = result.resources[0]
        # TODO: Возможно нужен предварительный fetch
        ext_refs = d1.relationships.external_references
        result = ext_refs.filter(Filter(title='Hep'))
        assert len(result.resources) == 1


article_test_schema = \
    {
        'articles': {
            'properties': {
                'title': {'type': 'string'},
                'extra-attribute': {'type': ['string', 'null']},
                'nested1': {'type': 'object', 'properties':
                    {
                        'other': {'type': ['string', 'null']},
                        'nested':
                            {'type': 'object', 'properties':
                                {'name': {'type': 'string'},
                                 'other': {'type': ['string', 'null']},
                                 }}}},
                'nested2': {'type': 'object', 'properties':
                    {
                        'other': {'type': ['null', 'string']},
                        'nested':
                            {'type': 'object', 'properties':
                                {'name': {'type': ['null', 'string'],
                                          'other': {'type': ['string', 'null']},
                                          }}}}}
            },
        }
    }


@pytest.mark.asyncio
async def test_attribute_checking_from_schema(mocked_fetch):
    async with Session('http://localhost:8080/', schema=article_test_schema) as s:
        doc = await s.get('articles')
        article = doc.resource
        assert article.title.startswith('JSON API paints')

        # Extra attribute that is in schema but not in data
        assert article.extra_attribute is None
        with pytest.raises(AttributeError):
            attr = article.extra_attribute_2

        # nested1 is in the test data
        with pytest.raises(AttributeError):
            attr = article.nested1.nested.a
        with pytest.raises(AttributeError):
            attr = article.nested1.a
        with pytest.raises(AttributeError):
            attr = article.a
        assert article.nested1.nested.name == 'test'
        assert article.nested1.nested.other is None
        assert article.nested1.other is None

        # nested2 is not in the test data
        with pytest.raises(AttributeError):
            attr = article.nested2.nested.a
        with pytest.raises(AttributeError):
            attr = article.nested2.a

        assert len(article.nested2) == 2  # There are still the items that were specified in schema

        assert article.nested2.nested.name is None
        assert len(article.nested2.nested) == 1


@pytest.mark.asyncio
async def test_schema_validation(mocked_fetch):
    schema2 = article_test_schema.copy()
    schema2['articles']['properties']['title']['type'] = 'number'
    s = Session('http://localhost:8080/', schema=schema2)

    with pytest.raises(ValidationError) as e:
        article = await s.get('articles')
        #article.title.startswith('JSON API paints')
    assert 'is not of type \'number\'' in str(e.value)
    await s.close()


def make_patch_json(ids, type_, field_name=None):
    if isinstance(ids, list):
        if isinstance(ids[0], tuple):
            content = {'data': [{'id': str(i), 'type': str(j)} for i, j in ids]}
        else:
            content = {'data': [{'id': str(i), 'type': type_} for i in ids]}
    elif ids is None:
        content = {'data': None}
    else:
        content = {'data': {'id': str(ids), 'type': type_}}

    data = {'data': {'type': 'articles',
                     'id': '1',
                     'attributes': {},
                     'relationships':
                         {
                             field_name or type_: content
                         }}}
    return data


@pytest.mark.asyncio
async def test_posting_successfull_async(mock_req_async, mock_update_resource):
    s = Session('http://localhost:80801/api', schema=api_schema_all)
    a = s.create('leases')
    assert a.is_dirty
    a.lease_id = '1'
    a.active_status = 'pending'
    a.reference_number = 'test'
    a.valid_for.start_datetime = 'asdf'
    await a.commit()

    agr_data = \
        {'data': {'type': 'leases',
                  'attributes': {'leaseId': '1', 'activeStatus': 'pending',
                                 'referenceNumber': 'test',
                                 'validFor': {'start-datetime': 'asdf'},
                                 },
                  'relationships': {}}}


    mock_req_async.assert_called_once_with('post', 'http://localhost:80801/api/leases',
                                     agr_data)
    await s.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('commit', [0, 1])
@pytest.mark.parametrize('kw_format', [0, 1])
async def test_posting_successfull_with_predefined_fields(kw_format, commit, mock_req_async, mocker):
    mocker.patch('jsonapi_client.session.Session.read')
    s = Session('http://localhost:80801/api', schema=api_schema_all)

    kwargs1 = dict(valid_for__start_datetime='asdf')
    kwargs2 = dict(valid_for={'start-datetime':'asdf'})

    a = s.create('leases',
                 lease_id='1',
                 active_status='pending',
                 reference_number='test',
                 lease_items=['1'],
                 **kwargs1 if kw_format else kwargs2
                 )
    if commit:
        await a.commit()
    assert a.is_dirty != commit

    if not commit:
        with mock.patch('jsonapi_client.session.Session.read'):
            await a.commit()

    agr_data = \
        {'data': {'type': 'leases',
                  'attributes': {'leaseId': '1', 'activeStatus': 'pending',
                                 'referenceNumber': 'test',
                                 'validFor': {'startDatetime': 'asdf'},
                                 },
                  'relationships': {'leaseItems': {'data': [{'id': '1',
                                                        'type': 'lease-items'}]},
                                    }}}

    mock_req_async.assert_called_once_with('post', 'http://localhost:80801/api/leases',
                                     agr_data)
    await s.close()


@pytest.mark.asyncio
async def test_create_with_default(mock_req_async):
    test_schema = \
        {
            'articles': {
                'properties': {
                    'testfield1': {'type': 'string', 'default': 'default'},
                    'testfield2': {'type': 'string', 'default': 'default'},
                }
            }
        }

    async with Session('http://localhost:8080/', schema=test_schema) as s:
        a = await s.create('articles', fields={'testfield1': 'test', 'testfield2': 'test'})
        assert a.testfield1 == 'test'
        assert a.testfield2 == 'test'

        with mock.patch('jsonapi_client.session.Session.read'):
            await a.commit()

        a2 = s.create('articles', fields={'testfield1': 'test'})
        assert a2.testfield1 == 'test'
        assert a2.testfield2 == 'default'

        with mock.patch('jsonapi_client.session.Session.read'):
            await a2.commit()

underscore_schema = \
    {
        'articles': {
            'properties': {
                'with_underscore': {'type': 'string'},
                'with-dash': {'type': 'string'},
            }
        }
    }


@pytest.mark.asyncio
async def test_create_with_underscore(mock_req_async):
    async with Session('http://localhost:8080/', schema=underscore_schema) as s:
        a = await s.create('articles',
                     fields={'with-dash': 'test', 'with_underscore': 'test2'}
        )
        assert 'with_underscore' in a._attributes
        assert 'with-dash' in a._attributes

        with mock.patch('jsonapi_client.session.Session.read'):
            await a.commit()


@pytest.mark.asyncio
async def test_create_with_underscore2(mock_req_async):
    async with Session('http://localhost:8080/', schema=underscore_schema) as s:
        a = await s.create('articles', with_dash='test',
                     fields={'with_underscore': 'test2'}
        )
        assert 'with_underscore' in a._attributes
        assert 'with-dash' in a._attributes

        with mock.patch('jsonapi_client.session.Session.read'):
            await a.commit()


@pytest.mark.asyncio
async def test_posting_relationships(mock_req_async, article_schema):
    if not article_schema:
        return

    s = Session('http://localhost:8080/', schema=article_schema)
    a = await s.create('articles',
            title='Test article',
            comments=[ResourceTuple(i, 'comments') for i in ('5', '12')],
            author=ResourceTuple('9', 'people'),
            comments_or_authors=[ResourceTuple('9', 'people'), ResourceTuple('12', 'comments')]
    )
    with mock.patch('jsonapi_client.session.Session.read'):
        await a.commit()


@pytest.mark.asyncio
async def test_posting_with_null_to_one_relationship(mock_req_async, article_schema):
    if not article_schema:
        return

    s = Session('http://localhost:8080/', schema=article_schema)
    a = s.create('articles',
            title='Test article',
            comments=[],
            author=None,
            comments_or_authors=[]
    )
    with mock.patch('jsonapi_client.session.Session.read'):
        await a.commit()
    await s.close()


@pytest.mark.asyncio
async def test_posting_successfull_without_schema(mock_req_async, mock_update_resource):
    s = Session('http://localhost:80801/api')
    a = s.create('leases')

    a.lease_id = '1'
    a.active_status = 'pending'
    a.reference_number = 'test'

    a.create_map('valid_for')  # Without schema we need to do this manually

    a.valid_for.start_datetime = 'asdf'
    await a.commit()

    agr_data = \
        {'data': {'type': 'leases',
                  'attributes': {'leaseId': '1', 'activeStatus': 'pending',
                                 'reference-number': 'test',
                                 'validFor': {'startDatetime': 'asdf'}},
                  'relationships': {}}}

    mock_req_async.assert_called_once_with('post', 'http://localhost:80801/api/leases',
                                     agr_data)
    await s.close()


@pytest.mark.asyncio
async def test_posting_post_validation_error():
    async with Session('http://localhost:80801/api', schema=api_schema_all) as s:
        a = s.create('leases')
        a.lease_id = '1'
        a.active_status = 'blah'
        a.reference_number = 'test'
        a.valid_for.start_datetime='asdf'
        with pytest.raises(jsonschema.ValidationError):
            await a.commit()


@pytest.mark.asyncio
async def test_relationship_manipulation_async(mock_req_async, mocked_fetch, article_schema, mock_update_resource):
    s = Session('http://localhost:80801/', schema=article_schema)

    doc = await s.get('articles')
    article = doc.resource

    assert article.author._resource_identifier.id == '9'
    if article_schema:
        assert article.author.type == 'people'
    # article.author = '10' # assigning could be done directly.
    # This would go through ResourceObject.__setattr__ and
    # through RelationshipDict.__setattr__, where it goes to
    # Relationship.set() method
    # But does pycharm get confused with this style?

    if article_schema:
        article.author = '10'  # to one.
    else:
        article.author.set('10', 'people')
    assert article.author.is_dirty == True
    assert 'author' in article.dirty_fields

    await article.commit()
    mock_req_async.assert_called_once_with('patch', 'http://example.com/articles/1',
                                     make_patch_json('10', 'people', field_name='author'))
    mock_req_async.reset_mock()
    assert not article.dirty_fields
    assert not article.author.is_dirty

    #assert article.author.value == '10'
    if article_schema:
        assert article.comments.type == 'comments'
        article.comments = ['5', '6']  # to many
    else:
        with pytest.raises(TypeError):
            article.comments = ['5', '6']

        article.comments.set(['5', '6'], 'comments')  # to many

    assert article.comments.is_dirty
    await article.commit()
    mock_req_async.assert_called_once_with('patch', 'http://example.com/articles/1',
                                     make_patch_json([5, 6], 'comments'))
    mock_req_async.reset_mock()

    #assert article.comments.value == ['5', '6']

    # Test .fields attribute proxy
    article.fields.comments.set(['6', '7'], 'comments')
    await article.commit()
    mock_req_async.assert_called_once_with('patch', 'http://example.com/articles/1',
                                     make_patch_json([6, 7], 'comments'))
    mock_req_async.reset_mock()

    #assert article.comments.value == ['6', '7']

    if article_schema:
        article.comments.add('8')  # id is sufficient as we know the type from schema
    else:
        with pytest.raises(TypeError):
            article.comments.add('8')  # id is sufficient as we know the type from schema
        article.comments.add('8', 'comments')
    article.comments.add('9', 'comments')  # But we can supply also type just in case we don't have schema available
    await article.commit()
    mock_req_async.assert_called_once_with('patch', 'http://example.com/articles/1',
                                     make_patch_json([6, 7, 8, 9], 'comments'))
    mock_req_async.reset_mock()

    #assert article.comments.value == ['6', '7', '8', '9']
    if article_schema:
        article.comments.add(['10','11'])
    else:
        with pytest.raises(TypeError):
            article.comments.add(['10','11'])
        article.comments.add(['10', '11'], 'comments')
    #assert article.comments.value == ['6', '7', '8', '9', '10', '11']
    await article.commit()

    mock_req_async.assert_called_once_with('patch', 'http://example.com/articles/1',
                                     make_patch_json([6, 7, 8, 9, 10, 11],
                                                           'comments'))
    mock_req_async.reset_mock()
    await s.close()


@pytest.mark.asyncio
async def test_relationship_manipulation_alternative_api(mock_req_async, mocked_fetch, article_schema, mock_update_resource):
    async with Session('http://localhost:80801/', schema=article_schema) as s:
        doc = await s.get('articles')
        article = doc.resource

        # Test alternative direct setting attribute via RelationshipDict's __setattr__
        # This does not look very nice with 'clever' IDE that gets totally confused about
        # this.

        oc1, oc2 = article.comments

        if article_schema:
            assert article.relationships.comments.type == 'comments'
            article.comments = ['5', '6']  # to many
        else:
            with pytest.raises(TypeError):
                article.relationships.comments = ['5', '6']
            with pytest.raises(TypeError):
                article.comments = ['5', '6']
            article.comments = [ResourceTuple(i, 'comments') for i in ['5', '6']]

        await article.commit()
        mock_req_async.assert_called_once_with('patch', 'http://example.com/articles/1',
                                         make_patch_json([5, 6], 'comments'))
        mock_req_async.reset_mock()

        #assert article.relationships.comments.value == ['5', '6']

        # ***** #
        if article_schema:
            assert article.relationships.comments.type == 'comments'
            article.comments = ['6', '7']  # to many
        else:
            with pytest.raises(TypeError):
                article.relationships.comments = ['6', '7']
            with pytest.raises(TypeError):
                article.comments = ['5', '6']
            #article.relationships.comments.set(['6', '7'], 'comments')
            article.comments = [ResourceTuple(i, 'comments') for i in ['6', '7']]

        await article.commit()
        mock_req_async.assert_called_once_with('patch', 'http://example.com/articles/1',
                                         make_patch_json([6, 7], 'comments'))
        mock_req_async.reset_mock()

        #assert article.relationships.comments.value == ['6', '7']

        # Set resourceobject

        if article_schema:
            assert article.relationships.comments.type == 'comments'
            article.comments = oc1, oc2
        else:
            article.relationships.comments = oc1, oc2
            article.comments = oc1, oc2


        await article.commit()
        mock_req_async.assert_called_once_with('patch', 'http://example.com/articles/1',
                                         make_patch_json([oc1.id, oc2.id], 'comments'))
        mock_req_async.reset_mock()

        #assert article.relationships.comments.value == [str(i) for i in [oc1.id, oc2.id]]


        # Let's test also .fields AttributeProxy
        if article_schema:
            assert article.relationships.comments.type == 'comments'
            article.fields.comments = ['7', '6']  # to many
        else:
            with pytest.raises(TypeError):
                article.fields.comments = ['7', '6']
            article.relationships.comments.set(['7', '6'], 'comments')

        await article.commit()
        mock_req_async.assert_called_once_with('patch', 'http://example.com/articles/1',
                                         make_patch_json([7, 6], 'comments'))
        mock_req_async.reset_mock()

        #assert article.relationships.comments.value == ['7', '6']


class SuccessfullLeaseResponse:
    status_code = 200
    headers = {}
    content = ''

    @classmethod
    def json(cls):
        return {
            'data': {
                'id': 'qvantel-lease1',
                'type': 'leases',
                'attributes': {
                    'validFor': {
                        'newField': 'something-new',
                        'startDatetime': 'something-else'
                    }
                },
                'relationships': {
                    'externalReferences': {
                        'data': [
                            {
                                'id': 'qvantel-lease1-extref',
                                'type': 'externalReferences'},
                            {
                                'id': '1',
                                'type': 'externalReferences'},
                            {
                                'id': '2',
                                'type': 'externalReferences'},
                            {
                                'id': '3',
                                'type': 'externalReferences'}
                        ]
                    }
                }
            }
        }


@pytest.mark.asyncio
async def test_set_custom_request_header_async_get_session():
    patcher = mock.patch('aiohttp.ClientSession')
    client_mock = patcher.start()
    request_kwargs = {'headers': {'Foo': 'Bar', 'X-Test': 'test'}}
    s = Session(
        'http://localhost',
        schema=leases,
        request_kwargs=request_kwargs
    )
    client_mock().get.return_value = SuccessfullLeaseResponse
    with pytest.raises(AttributeError):
        await s.get('leases', 1)

    await s.close()
    assert client_mock().get.called
    args = client_mock().get.call_args
    assert args[1]['headers']['Foo'] == 'Bar'
    assert args[1]['headers']['X-Test'] == 'test'
    patcher.stop()


@pytest.mark.asyncio
async def test_posting_async_with_custom_header(loop, session):
    response = ClientResponse('post', URL('http://localhost/api/leases'),
                              request_info=mock.Mock(),
                              writer=mock.Mock(),
                              continue100=None,
                              timer=TimerNoop(),
                              traces=[],
                              loop=loop,
                              session=session,
                              )

    response._headers = {'Content-Type': 'application/vnd.api+json'}
    response._body = json.dumps({'errors': [{'title': 'Internal server error'}]}).encode('UTF-8')
    response.status = 500

    patcher = mock.patch('aiohttp.ClientSession.request')
    request_mock = patcher.start()
    request_mock.return_value = response
    request_kwargs = {'headers': {'Foo': 'Bar', 'X-Test': 'test'}, 'something': 'else'}
    s = Session(
        'http://localhost/api',
        schema=api_schema_all,
        request_kwargs=request_kwargs
    )
    a = s.create('leases')
    assert a.is_dirty
    a.lease_id = '1'
    a.active_status = 'pending'
    a.reference_number = 'test'
    a.valid_for.start_datetime = 'asdf'
    with pytest.raises(DocumentError):
        await a.commit()

    assert request_mock.called
    args = request_mock.call_args
    assert args[1]['headers']['Content-Type'] == 'application/vnd.api+json'
    assert args[1]['headers']['Foo'] == 'Bar'
    assert args[1]['headers']['X-Test'] == 'test'
    assert args[1]['something'] == 'else'
    patcher.stop()


@pytest.mark.asyncio
async def test_error_handling_async_get(loop, session):
    response = ClientResponse('get', URL('http://localhost:8080/invalid'),
                              request_info=mock.Mock(),
                              writer=mock.Mock(),
                              continue100=None,
                              timer=TimerNoop(),
                              traces=[],
                              loop=loop,
                              session=session,
                              )
    response._headers = {'Content-Type': 'application/vnd.api+json'}
    response._body = json.dumps({'errors': [{'title': 'Resource not found'}]}).encode('UTF-8')
    response.status = 404

    patcher = mock.patch('aiohttp.ClientSession')
    client_mock = patcher.start()
    s = Session('http://localhost', schema=leases)
    client_mock().get.return_value = response
    with pytest.raises(DocumentError) as exp:
        await s.get('invalid')

    assert str(exp.value) == 'Error 404: Resource not found'
    patcher.stop()


@pytest.mark.asyncio
async def test_error_handling_posting_async(loop, session):
    response = ClientResponse('post', URL('http://localhost:8080/leases'),
                              request_info=mock.Mock(),
                              writer=mock.Mock(),
                              continue100=None,
                              timer=TimerNoop(),
                              traces=[],
                              loop=loop,
                              session=session,
                              )
    response._headers = {'Content-Type': 'application/vnd.api+json'}
    response._body = json.dumps({'errors': [{'title': 'Internal server error'}]}).encode('UTF-8')
    response.status = 500

    patcher = mock.patch('aiohttp.ClientSession.request')
    request_mock = patcher.start()
    s = Session(
        'http://localhost:8080',
        schema=api_schema_all,
    )
    request_mock.return_value = response

    a = s.create('leases')
    assert a.is_dirty
    a.lease_id = '1'
    a.active_status = 'pending'
    a.reference_number = 'test'
    with pytest.raises(DocumentError) as exp:
        await a.commit()

    assert str(exp.value) == 'Could not POST (500): Internal server error'
    patcher.stop()
