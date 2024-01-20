import json
import logging
import os
from configparser import SafeConfigParser as ConfigParser

from ckan.lib.base import config
from ckan.model import Session
from ckan.model.group import Group, Member
from ckan.plugins import toolkit

from ckanext.dcatapit.dcat.const import THEME_BASE_URI
from ckanext.dcatapit.schema import FIELD_THEMES_AGGREGATE

log = logging.getLogger(__name__)

DCATAPIT_THEMES_MAP = 'ckanext.dcatapit.nonconformant_themes_mapping.file'
DCATAPIT_THEMES_MAP_SECTION = 'terms_theme_mapping'
import six

subt=''

def themes_to_aggr_json(themes: list) -> str:
    aggr = []
    subt=''
    for i in themes:
     if i == 'subthemes':
      subt=str(themes[i])
      #log.warning('Subthemes i: %s',i)
    for name in themes or []:
        #log.warning('Themes json è: %s',themes)
        #log.warning('name è: %s',name)
        if isinstance(name, str): 
         name = name.split('/')[-1]  # if it's a URL, only take the final name
         aggr.append({'theme': name.upper(), 'subthemes': []})
      #  else:
       #  aggr.append({'theme': themes['theme'].upper(), 'subthemes': themes['subthemes']})
    #log.warning('Themes json aggr è: %s',json.dumps(aggr))
    return json.dumps(aggr)
 
def theme_aggr_to_theme_uris(aggregated_themes: list) -> list:
    return [theme_name_to_uri(agg.get('theme')) for agg in aggregated_themes]


def theme_name_to_uri(theme_name: str) -> str:
    if isinstance(theme_name, six.string_types):
     if theme_name.startswith('http'):
        log.warning(f'Theme name "{theme_name}" is already a URI')
        return theme_name
    return THEME_BASE_URI + theme_name


def theme_names_to_uris(names: list) -> list:
    return [theme_name_to_uri(name) for name in names]


def theme_aggrs_unpack(aggrs: list) -> (list, list):
    themes = []
    sub = []
    for aggr in aggrs:
        themes.append(theme_name_to_uri(aggr['theme']))
        sub.extend(aggr['subthemes'])
        log.warning('unpack theme subtheme',aggr)
    return themes, sub


def themes_parse_to_uris(raw) -> list:
    if not raw:
        return []

    #log.debug(f'Parsing themes field: {raw}')
    try:
        themes = json.loads(raw)
        themes_list = theme_names_to_uris(themes)
    except (TypeError, ValueError) as e:
        log.warning(f'Error parsing themes: {e} -- {raw}')
        if isinstance(raw, (list, tuple,)):
            log.debug(f'using themes list: {raw}')
            themes_list = theme_names_to_uris(raw)
        elif isinstance(raw, str):
            log.warning(f'Trying parsing old format: {raw}')
            themes_list = theme_names_to_uris(
                [name for name in raw.strip('{}').split(',')])
        else:
            log.error('No valid themes found')
            themes_list = []
    #log.debug('Parsing themes_list %s:', themes_list)
#    return theme_names_to_uris(raw)
    return themes_list


def _map_themes_json(fdesc):
    out = {}

    try:
        data = json.load(fdesc)
    except UnicodeDecodeError:
        # fix for docker env
        try:
            data = json.load(fdesc, encoding='latin-1')
        except Exception as err:
            log.error('Cannot parse themes from json:', exc_info=err)
            return out

    for map_item in data['data']:
        map_to = map_item['syn'][0]
        for syn in map_item['syn'][1:]:
            try:
                out[syn].append(map_to)
            except KeyError:
                out[syn] = [map_to]
    #log.warning('Data for parse themes: %s', data['data'])
    return out


def _map_themes_ini(fdesc):
    c = ConfigParser()
    c.readfp(fdesc)
    out = {}
    section_name = 'dcatapit:{}'.format(DCATAPIT_THEMES_MAP_SECTION)
    for theme_in, themes_out in c.items(section_name, raw=True):
        out[theme_in] = [t.strip() for t in themes_out.replace('\n', ',').split(',') if t.strip()]
        log.warning('Data for theme_ins: %s', out[theme_in])
    return out


def _load_mapping_data():
    """
    Retrives mapping data depending on configuration.

    :returns: dict with from->[to] mapping or None, if no configuration is available
    """
    fpath = config.get(DCATAPIT_THEMES_MAP)
    if not fpath:
        return
    if not os.path.exists(fpath):
        log.warning("Mapping themes in %s doesn't exist", fpath)
        return
    base, ext = os.path.splitext(fpath)
    if ext == '.json':
        handler = _map_themes_json
    else:
        handler = _map_themes_ini

    with open(fpath) as f:
        map_data = handler(f)

        return map_data


def _get_new_themes(from_groups, map_data, add_existing=True):
    if not from_groups:
        return

    new_themes = []
    # if theme is not in mapping list, keep it
    # otherwise, replace it with mapped themes
    for group in from_groups:
        map_to = map_data.get(group)
        if map_to:
            new_themes.extend(map_to)
        else:
            if add_existing:
                new_themes.append(group)
    # do not update if themes are the same
    if set(from_groups) == set(new_themes):
        return
    return list(set(new_themes))


def map_nonconformant_groups(harvest_object):
    """
    Adds themes to fetched data
    """
    themes_data = _load_mapping_data()
    if not themes_data:
        return

    data = json.loads(harvest_object.content)
    _groups = data.get('groups')
    if not _groups:
        return

    groups = [g['name'] for g in _groups]
    groups.extend([g['display_name'] for g in _groups if 'display_name' in g])

    new_themes = _get_new_themes(groups, themes_data, add_existing=False)
    if not new_themes:
        return

    # ensure themes are upper-case, otherwise will be discarded by validators


    extra = data.get('extras') or []

    aggr = themes_to_aggr_json(new_themes)
    _set_extra(extra, FIELD_THEMES_AGGREGATE, aggr)
    data[FIELD_THEMES_AGGREGATE] = aggr

    theme_list = json.dumps([theme_name_to_uri(name) for name in new_themes])
    _set_extra(extra, 'theme', theme_list)
    data['theme'] = theme_list
    log.warning('theme_list non conformant %s', theme_list)
    data['extras'] = extra

    harvest_object.content = json.dumps(data)
    Session.add(harvest_object)
    Session.flush()


def _get_extra(extras, key):
    return next((x for x in extras if x['key'] == key), None)


def _get_extra_value(extras, key):
    return next((x['value'] for x in extras if x['key'] == key), None)


def _set_extra(extras, key, value):
    x = _get_extra(extras, key)
    if x:
        x['value'] = value
    else:
        extras.append({'key': key, 'value': value})
    return x is not None

"""
Theme to Group mapping
======================

This allows to automatically assing Groups to Dataset based on used themes.
This will work for harvested Datasets and with Datasets created with web ui.


Configuration
-------------

 * add `dcatapit_theme_group_mapper` plugin to `ckan.plugins`

 * set `ckanext.dcatapit.theme_group_mapping.file` - path to mapping file.
        See below for contents

 * set `ckanext.dcatapit.theme_group_mapping.add_new_groups` to `true` if you want to
        enable automatic Group creation if one is missing, but it's defined in mapping

Mapping file
------------

Mapping file is .ini-style map configuration. Contents should be following:

 * it should have  `dcatapit:theme_group_mapping` section

 * each key is name of theme

 * value is a list of groups to assign to. It can be separated with comas or each item can be in new line.

Sample file contents:

.. code::

 [dcatapit:theme_group_mapping]
 thememap1 = somegroup1
     somegroup2, existing-group

If file is specified in configuration, but is not accessible by ckan, warning will be logged.

"""


MAPPING_SECTION = 'dcatapit:theme_group_mapping'
DCATAPIT_THEME_TO_MAPPING_SOURCE = 'ckanext.dcatapit.theme_group_mapping.file'
DCATAPIT_THEME_TO_MAPPING_ADD_NEW_GROUPS = 'ckanext.dcatapit.theme_group_mapping.add_new_groups'


def get_theme_to_groups():
    """
    Returns dictionary with groups for themes
    """
  # non riesce a caricare la configurazione del ckan.ini per ckanext.dcatapit.theme_group_mapping.file
  # patch per inserimento manuale. da risolvere.
 #    fname = config.get(DCATAPIT_THEME_TO_MAPPING_SOURCE)
    fname = '/srv/app/patches/theme_to_group.ini'
    if not fname:
        return
    if not os.path.exists(fname):
        log.warning('Cannot parse theme mapping, no such file: %s', fname)
        return
    return import_theme_to_group(fname)


def _clean_groups(package):
    """
    Clears package's groups
    """
    if isinstance(package, dict):
        package_id = package['id']
    else:
        package_id = package.id
    Session.query(Member).filter(Member.table_name == 'package',
                                 Member.table_id == package_id,
                                 Member.capacity != 'admin')\
        .update({'state': 'deleted'})


def _add_groups(package_id, groups):
    """
    Adds groups to package
    """
    for g in groups:
        if g.id is None:
            raise ValueError('No id in group %s' % g)

        q = Session.query(Member).filter_by(state='active',
                                            table_id=package_id,
                                            group_id=g.id,
                                            table_name='package')
        # this group is already added to package, skipping
        # note: this will work with groups flushed to db
        if Session.query(q.exists()).scalar():
            continue

        member = Member(state='active',
                        table_id=package_id,
                        group_id=g.id,
                        group=g,
                        table_name='package')
        Session.add(member)


def _get_group_from_session(gname):
    """
    If Group was created within current session, get
    it from cache instead of db.

    This exists because new, uncommited/unflushed objects are
    not accessible by Session.query.
    """
    for obj in Session.new:
        if isinstance(obj, Group):
            if obj.name == gname:
                return obj

def freeze(d):
    if isinstance(d, dict):
        return frozenset((key, freeze(value)) for key, value in d.items())
    elif isinstance(d, list):
        return tuple(freeze(value) for value in d)
    return d

def populate_theme_groups(instance, clean_existing=False):
    """
    For given instance, it finds groups from mapping corresponding to
    Dataset's themes, and will assign dataset to those groups.

    Existing groups will be removed, if clean_existing is set to True.

    This utilizes `ckanext.dcatapit.theme_group_mapping.add_new_groups`
    configuration option. If it's set to true, and mapped group doesn't exist,
    new group will be created.
    """
    add_new = toolkit.asbool(config.get(DCATAPIT_THEME_TO_MAPPING_ADD_NEW_GROUPS))
    themes = []
    for ex in (instance.get('extras') or []):
        if ex['key'] == FIELD_THEMES_AGGREGATE:
            _t = ex['value']
            if isinstance(_t, list):
                themes.extend(_t)
            else:
                try:
                    tval = json.loads(_t)
                except Exception:
                    log.warning(f'Trying old themes format for {_t}')
                    tval = [{'theme': t, 'subthemes': []} for t in _t.strip('{}').split(',')]

                for tv in tval:
                    themes.append(tv['theme'])

            break  # we don't need any other info - if there are 'themes' is ok to bypass them

        elif ex['key'] == 'theme':
            _t = ex['value']
            if isinstance(_t, list):
                themes.extend(_t)
            else:
                try:
                    tval = json.loads(_t)
                except Exception:
                    log.warning(f'Trying old themes format for {_t}')
                    if _t is not None:
                     tval = _t.strip('{}').split(',')

                themes.extend(tval)
            # dont break the for loop: if aggregates are there, they get precedence

    if not themes:
         #log.debug('no theme from %s', instance)
        return instance
    theme_map = get_theme_to_groups()

    if not theme_map:
        log.warning('Theme to group map is empty')
        return instance
    if not isinstance(themes, list):
        themes = [themes]
    all_groups = set()
    for theme in themes:
#frozenset(dict_key.items())
        if not isinstance(theme, str):
         #theme.pop('subthemes')
        #log.warning('Theme in theme_map %s',theme)
         _groups = theme_map.get(theme['theme'])
        else:
         _groups = theme_map.get(theme)
        #log.warning('_groups %s',_groups)
        #log.warning('themes %s',themes)
        if not _groups:
            continue
        all_groups = all_groups.union(set(_groups))
    if clean_existing:
        _clean_groups(instance)
    groups = []
    for gname in all_groups:
        gname = gname.strip()
        if not gname:
            continue
        group = Group.get(gname) or _get_group_from_session(gname)
        if add_new and group is None:
            group = Group(name=gname)
            Session.add(group)
        if group:
            groups.append(group)

    if Session.new:
        # flush to db, refresh with ids
        Session.flush()
        groups = [(Group.get(g.name) if g.id is None else g) for g in groups]
    _add_groups(instance['id'], set(groups))

    Session.flush()
    return instance


def import_theme_to_group(fname):
    """
    Import theme to group mapping configuration from path

    Function will parse .ini file and populate mapping tables.

    This function will make commits internally, so caller should create fresh revision before commiting later.

    Sample configuration file:

[dcatapit:theme_group_mapping]

# can be one line of values separated by coma
Economy = economy01, economy02, test01, test02

# can be per-line list
Society = society
    economy01
    other02

# or mixed
OP_DATPRO = test01
    test02, test03, dupatest

    """
    fpath = os.path.abspath(fname)
    conf = ConfigParser()
    # otherwise theme names will be lower-cased
    conf.optionxform = str
    conf.read([fpath])
    if not conf.has_section(MAPPING_SECTION):
        log.warning('Theme to groups mapping config: cannot find %s section in %s',
                    MAPPING_SECTION, fpath)
        return
    out = {}
    for theme_name, groups in conf.items(MAPPING_SECTION, raw=True):
        out[theme_name] = groups.replace('\n', ',').split(',')
        #log.info('prima del Read theme to group %s',out[theme_name])
    log.info('Read theme to groups mapping definition from %s. %s themes to map.', fpath, len(out.keys()))
    return out
