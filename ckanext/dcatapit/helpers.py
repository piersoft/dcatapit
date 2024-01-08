import datetime
import json
import logging

import ckan.lib.helpers as h
import ckan.plugins.toolkit as toolkit
from ckan.lib.base import config
from ckan.model import GroupExtra, Session
from ckan.plugins import PluginImplementations
from ckanext.harvest.model import HarvestObject
from markupsafe import Markup
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound

import ckanext.dcatapit.interfaces as interfaces
import ckanext.dcatapit.schema as dcatapit_schema
from ckanext.dcatapit.model.subtheme import Subtheme

log = logging.getLogger(__file__)

dateformats = [
    '%d-%m-%Y',
    '%Y-%m-%d',
    '%d-%m-%y',
    '%Y-%m-%d %H:%M:%S',
    '%d-%m-%Y %H:%M:%S',
    '%Y-%m-%dT%H:%M:%S'
]

# config param names
DCATAPIT_ENABLE_FORM_TABS = 'ckanext.dcatapit.form_tabs'
GEONAMES_USERNAME = 'geonames.username'
GEONAMES_LIMIT_TO = 'geonames.limits.countries'
DEFAULT_CTX = {'ignore_auth': True}
DEFAULT_ORG_CTX = DEFAULT_CTX.copy()
DEFAULT_ORG_CTX.update(dict((k, False) for k in ('include_tags',
                                                 'include_users',
                                                 'include_groups',
                                                 'include_extras',
                                                 'include_followers',)))


def get_dcatapit_package_schema():
    log.debug('Retrieving DCAT-AP_IT package schema fields...')
    return dcatapit_schema.get_custom_package_schema()


def get_dcatapit_organization_schema():
    log.debug('Retrieving DCAT-AP_IT organization schema fields...')
    return dcatapit_schema.get_custom_organization_schema()


def get_dcatapit_configuration_schema():
    log.debug('Retrieving DCAT-AP_IT configuration schema fields...')
    return dcatapit_schema.get_custom_config_schema()


def get_dcatapit_resource_schema():
    log.debug('Retrieving DCAT-AP_IT resource schema fields...')
    return dcatapit_schema.get_custom_resource_schema()


def get_vocabulary_items(vocabulary_name, keys=None, lang=None):
    try:
        tag_list = toolkit.get_action('tag_list')
        items = tag_list(data_dict={'vocabulary_id': vocabulary_name, 'all_fields': True})

        # log.warning(f'ITEMS {items}')
        tag_list = []
        for full_item in items:
            tag_id = full_item['id']
            tag_name = full_item['name']
            if keys:
                for key in keys:
                    if key == tag_name:
                        localized_tag_name = interfaces.get_localized_tag_name(tag_name, lang)
                        tag_list.append(localized_tag_name)
            else:
                localized_tag_name = interfaces.get_localized_tag_by_id(tag_id, lang)
                tag_list.append({'text': localized_tag_name, 'value': tag_name})

        return tag_list
    except toolkit.ObjectNotFound:
        return []


def get_vocabulary_item(vocabulary_name, key):
    return interfaces.get_localized_tag_name(key)


def get_dcatapit_license(license_type):
    return interfaces.get_license_for_dcat(license_type)


def get_package_resource_dcatapit_format_list(pkg_resources, fallback_lang=None):
    resources = []
    if pkg_resources:
        resources = h.dict_list_reduce(pkg_resources, 'format')

    package_res = []
    for resource in resources:
        localized_resource_name = interfaces.get_localized_tag_name(resource, fallback_lang)
        package_res.append(localized_resource_name)

    resources = package_res
    return resources


def get_localized_field_value(field=None, pkg_id=None, field_type='extra'):
    log.debug('Retrieving localized package field...')
    return interfaces.get_localized_field_value(field, pkg_id, field_type)


def get_resource_licenses_tree(value=None, lang=None):
    return interfaces.get_resource_licenses_tree(value, lang)


def list_to_string(_list, _format=None):
    if _list:
        _string = ''

        first_item = True
        for item in _list:
            if first_item:
                first_item = False
                element = item

                if _format:
                    element = format(element, _format)

                _string = _string + element
            else:
                element = item

                if _format:
                    element = format(element, _format)

                _string = _string + ', ' + item

        return _string


def couple_to_string(field_couples, pkg_dict):
    if field_couples and pkg_dict:
        _string = ''
        for couple in field_couples:
            if couple['name'] in pkg_dict:
                field_value = pkg_dict[couple['name']]
                if field_value and couple['label']:
                    _string = _string + ' ' + couple['label'] + ': ' + field_value

        return _string
    return None


def couple_to_html(field_couples, pkg_dict):
    if field_couples and pkg_dict:
        html_elements = []
        for couple in field_couples:
            couple_name = couple.get('name', None)

            if couple_name in pkg_dict:
                field_value = pkg_dict[couple_name]

                couple_format = couple.get('format', None)
                if couple_format:
                    couple_type = couple.get('type', None)
                    field_value = format(field_value, couple_format, couple_type)

                couple_label = couple.get('label', None)
                if field_value and couple_label:
                    html_elements.append(Markup(('<span style="font-weight:bold">%s: </span><span>%s</span>') % (couple_label, field_value)))

        return html_elements if len(html_elements) > 0 else []
    return []


def couple_to_dict(field_couples, pkg_dict):
    ret = []
    if field_couples and pkg_dict:
        for couple in field_couples:
            couple_name = couple.get('name', None)

            if couple_name in pkg_dict:
                field_value = pkg_dict[couple_name]

                couple_format = couple.get('format', None)
                if couple_format:
                    couple_type = couple.get('type', None)
                    field_value = format(field_value, couple_format, couple_type)

                couple_label = couple.get('label', None)
                if field_value and couple_label:
                    c = {'label': couple_label, 'value': field_value}
                    ret.append(c)

    return ret


def format(value, _format='%d-%m-%4Y', _type=None):
    # #################################################
    # TODO: manage here other formats if needed
    #      (ie. for type text, other date formats etc)
    # #################################################
    if _format and _type:
        if _type == 'date':
            date = None
            for dateformat in dateformats:
                date = validate_dateformat(value, dateformat)

                if isinstance(date, datetime.date):
                    try:
                        date = date.strftime(_format)
                        return date
                    except ValueError as err:
                        log.warning('cannot reformat %s value (from %s) to %s format: %s',
                                    date, value, _format, err, exc_info=err)
                    return value
        if _type == 'text':
            return value

    return value


def validate_dateformat(date_string, date_format):
    try:
        date = datetime.datetime.strptime(date_string, date_format)
        return date
    except ValueError:
        log.debug('Incorrect date format {0} for date string {1}'.format(date_format, date_string))
        return None


def json_load(val):
    try:
        return json.loads(val)
    except (TypeError, ValueError):
        pass


def json_dump(val):
    try:
        return json.dumps(val)
    except (TypeError, ValueError) as err:
        pass


def load_json_or_list(val):
    try:
        return json.loads(val)
    except (TypeError, ValueError):
        if val:
            return [{'identifier': v} for v in val.split(',')]


def get_geonames_config():
    out = {}
    uname = config.get(GEONAMES_USERNAME)
    limit_to = config.get(GEONAMES_LIMIT_TO)
    if uname:
        out['username'] = uname
    if limit_to:
        out['limit_to'] = limit_to
    return out


def get_localized_subtheme(subtheme_id, lang):
    return interfaces.get_localized_subtheme(subtheme_id, lang) or subtheme_id


def get_dcatapit_subthemes(lang):
    """
    Dump subthemes tree with localized lables for all themes
    """
    out = {}

    def _get_name(opt_val, depth):
        return '{} {}'.format('-' * depth, opt_val)

    for theme in Subtheme.get_theme_names():
        out[theme] = theme_l = []
        for opt, label in Subtheme.for_theme(theme, lang):
            theme_l.append({'name': _get_name(label, opt.depth),
                            'value': opt.uri})
    log.debug('helpers subthemes %s',out)
    return out


def dcatapit_string_to_aggregated_themes(value):
    """
    Dump subthemes from dataset dict, handle old format as well
    """
    log.debug('helpers value %s',value)
    out = []
    data = []
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        # old format: '{themecode1, themecode2, ...}'
        # no subthemes provided in the old format
        if isinstance(value, str):
            data = [{'theme': s, 'subthemes': []} for s in value.strip('{}').split(',')]
    if data:
        out.extend(data)
    log.debug('helpers aggregate_themes %s',out)
    return out


def dcatapit_string_to_localized_aggregated_themes(value, lang):
    """
    Load json with subthemes and get localized subtheme names. Used in template
    """
    data = dcatapit_string_to_aggregated_themes(value)
    out = []

    for item in data:
        localized_theme = interfaces.get_localized_tag_name(item['theme'], lang=lang)
        outitem = {'theme': localized_theme,
                   'subthemes': []}
        from_model = Subtheme.for_theme(item['theme'], lang)
        for st, label in from_model:
            if st.uri in item['subthemes']:
                outitem['subthemes'].append(label)
        out.append(outitem)
    log.debug('helpers aggregate_themes localized %s',out)
    return out


def get_organization_by_identifier(context, identifier):
    """
    quick'n'dirty way to get organization by rights holder's identifer
    from dcat rdf.
    """
    try:
        ge = Session.query(GroupExtra).filter_by(key='identifier',
                                                 value=identifier,
                                                 state='active')\
            .one()
    except MultipleResultsFound:
        raise
    except NoResultFound:
        ge = None
    if ge:
        # safety check
        assert ge.group_id is not None
        ctx = context.copy()
        ctx.update(get_org_context())

        return toolkit.get_action('organization_show')(context=ctx, data_dict={'id': ge.group_id})


def get_enable_form_tabs():
    conf_var = config.get(DCATAPIT_ENABLE_FORM_TABS)
    if conf_var is not None:
        return toolkit.asbool(conf_var)
    # default
    return True


def get_org_context():
    return DEFAULT_ORG_CTX.copy()


def get_icustomschema_fields():
    out = []
    for plugin in PluginImplementations(interfaces.ICustomSchema):
        extra_schema = plugin.get_custom_schema()

        for extra in extra_schema:
            extra['external'] = True
        out.extend(extra_schema)
    return out


def get_icustomschema_org_fields():
    out = []
    for plugin in PluginImplementations(interfaces.ICustomSchema):
        if hasattr(plugin, 'get_custom_org_schema'):
            extra_schema = plugin.get_custom_org_schema()

            for extra in extra_schema:
                extra['external'] = True
            out.extend(extra_schema)
    return out


def dataset_is_local(pkg_id):
    q = Session.query(HarvestObject).filter(HarvestObject.package_id == pkg_id).exists()
    is_remote = Session.query(q).scalar()
    return not is_remote
