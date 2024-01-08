import json
import logging

import ckanext.dcatapit.harvesters.utils as utils
from ckan import model
from ckan.model import Session
from ckan.plugins.core import SingletonPlugin
from ckanext.dcatapit import interfaces
from ckanext.dcatapit.model import License
from ckanext.spatial.harvesters.csw import CSWHarvester
from ckanext.spatial.model import (
    ISODocument,
    ISOElement,
    ISOKeyword,
    ISOResponsibleParty,
)

from ckanext.dcatapit.schema import FIELD_THEMES_AGGREGATE

log = logging.getLogger(__name__)


ISODocument.elements.append(
    ISOResponsibleParty(
        name='cited-responsible-party',
        search_paths=[
            'gmd:identificationInfo/gmd:MD_DataIdentification/gmd:citation/gmd:CI_Citation/gmd:citedResponsibleParty/gmd:CI_ResponsibleParty',
            'gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:citation/gmd:CI_Citation/gmd:citedResponsibleParty/gmd:CI_ResponsibleParty'
        ],
        multiplicity='1..*',
    )
)

ISODocument.elements.append(
    ISOElement(
        name='conformity-specification-title',
        search_paths=[
            'gmd:dataQualityInfo/gmd:DQ_DataQuality/gmd:report/gmd:DQ_DomainConsistency/gmd:result/gmd:DQ_ConformanceResult/gmd:specification/gmd:CI_Citation/gmd:title/gco:CharacterString/text()'
        ],
        multiplicity='1',
    ))

ISOKeyword.elements.append(
    ISOElement(
        name='thesaurus-title',
        search_paths=[
            'gmd:thesaurusName/gmd:CI_Citation/gmd:title/gco:CharacterString/text()',
        ],
        multiplicity='1',
    ))

ISOKeyword.elements.append(
    ISOElement(
        name='thesaurus-identifier',
        search_paths=[
            'gmd:thesaurusName/gmd:CI_Citation/gmd:identifier/gmd:MD_Identifier/gmd:code/gco:CharacterString/text()',
        ],
        multiplicity='1',
    ))


class DCATAPITCSWHarvester(CSWHarvester, SingletonPlugin):

    DEFAULT_CONFIG = {
        'dataset_themes': [{'theme': 'OP_DATPRO', 'subthemes': []}],
        'dataset_places': None,
        'dataset_languages': 'ITA',
        'frequency': 'UNKNOWN',
        'agents': {
            'publisher': {
                'code': 'temp_ipa',
                'role': 'publisher',
                'code_regex': {
                    'regex': '\(([^)]+)\:([^)]+)\)',
                    'groups': [2]  # optional, dependes by the regular expression
                },
                'name_regex': {
                    'regex': '([^(]*)(\(IPA[^)]*\))(.+)',
                    'groups': [1, 3]  # optional, dependes by the regular expression
                }
            },
            'owner': {
                'code': 'temp_ipa',
                'role': 'owner',
                'code_regex': {
                    'regex': '\(([^)]+)\:([^)]+)\)',
                    'groups': [2]  # optional, dependes by the regular expression
                },
                'name_regex': {
                    'regex': '([^(]*)(\(IPA[^)]*\))(.+)',
                    'groups': [1, 3]  # optional, dependes by the regular expression
                }
            },
            'author': {
                'code': 'temp_ipa',
                'role': 'author',
                'code_regex': {
                    'regex': '\(([^)]+)\:([^)]+)\)',
                    'groups': [2]  # optional, dependes by the regular expression
                },
                'name_regex': {
                    'regex': '([^(]*)(\(IPA[^)]*\))(.+)',
                    'groups': [1, 3]  # optional, dependes by the regular expression
                }
            }
        },
        'controlled_vocabularies': {
            'dcatapit_skos_theme_id': 'theme.data-theme-skos',
            'dcatapit_skos_places_id': 'theme.places-skos'
        }
    }

    def info(self):
        return {
            'name': 'DCAT_AP-IT CSW Harvester',
            'title': 'DCAT_AP-IT CSW Harvester',
            'description': 'DCAT_AP-IT Harvester for harvesting dcatapit fields from CWS',
            'form_config_interface': 'Text'
        }

    def get_package_dict(self, iso_values, harvest_object):
        package_dict = super(DCATAPITCSWHarvester, self).get_package_dict(iso_values, harvest_object)

        mapping_frequencies_to_mdr_vocabulary = self.source_config.get('mapping_frequencies_to_mdr_vocabulary',
                                                                       utils._mapping_frequencies_to_mdr_vocabulary)
        mapping_languages_to_mdr_vocabulary = self.source_config.get('mapping_languages_to_mdr_vocabulary',
                                                                     utils._mapping_languages_to_mdr_vocabulary)

        self._ckan_locales_mapping = self.source_config.get('ckan_locales_mapping') or utils._ckan_locales_mapping

        dcatapit_config = self.source_config.get('dcatapit_config', self.DEFAULT_CONFIG)

        # if dcatapit_config and not all(name in dcatapit_config for name in self._dcatapit_config):
        #    dcatapit_config = self._dcatapit_config
        #    log.warning('Some keys are missing in dcatapit_config configuration property, \
        #        keyes to use are: dataset_theme, dataset_language, agent_code, frequency, \
        #        agent_code_regex, org_name_regex and dcatapit_skos_theme_id. Using defaults')
        # elif not dcatapit_config:
        #    dcatapit_config = self._dcatapit_config

        controlled_vocabularies = dcatapit_config.get(
            'controlled_vocabularies',
            self.DEFAULT_CONFIG.get('controlled_vocabularies'))
        agents = dcatapit_config.get(
            'agents',
            self.DEFAULT_CONFIG.get('agents'))

        # ------------------------------#
        #    MANDATORY FOR DCAT-AP_IT   #
        # ------------------------------#

        #  -- identifier -- #
        identifier = iso_values['guid']
        package_dict['extras'].append({'key': 'identifier', 'value': identifier})

        default_ipa = identifier.split(':')[0] if ':' in identifier else None

        #  -- theme -- #
        dataset_themes = []
        if iso_values['keywords']:
            default_vocab_id = self.DEFAULT_CONFIG.get('controlled_vocabularies').get('dcatapit_skos_theme_id')
            dataset_themes = utils.get_controlled_vocabulary_values(
                'eu_themes',
                controlled_vocabularies.get('dcatapit_skos_theme_id', default_vocab_id), iso_values['keywords'])

        if dataset_themes:
            dataset_themes = list(set(dataset_themes))
            dataset_themes = [{'theme': str(l), 'subthemes': []} for l in dataset_themes]

        else:
            dataset_themes = dcatapit_config.get('dataset_themes')

        if isinstance(dataset_themes, str):
            dataset_themes = [{'theme': dt} for dt in dataset_themes.strip('{}').split(',')]

        log.info('Metadata harvested dataset themes: %r', dataset_themes)
        package_dict['extras'].append({'key': FIELD_THEMES_AGGREGATE, 'value': json.dumps(dataset_themes)})

        #  -- publisher -- #
        agent_name, agent_code = utils.get_responsible_party(
            iso_values['cited-responsible-party'],
            agents.get('publisher',
                       self.DEFAULT_CONFIG.get('agents').get('publisher')))
        package_dict['extras'].append({'key': 'publisher_name', 'value': agent_name})
        package_dict['extras'].append({'key': 'publisher_identifier', 'value': agent_code or default_ipa})

        #  -- modified -- #
        revision_date = iso_values['date-updated'] or iso_values['date-released']
        package_dict['extras'].append({'key': 'modified', 'value': revision_date})

        #  -- frequency -- #
        package_dict['extras'].append({
            'key': 'frequency',
            'value': mapping_frequencies_to_mdr_vocabulary.get(
                iso_values['frequency-of-update'],
                dcatapit_config.get('frequency', self.DEFAULT_CONFIG.get('frequency')))})

        #  -- rights_holder -- #
        agent_name, agent_code = utils.get_responsible_party(
            iso_values['cited-responsible-party'],
            agents.get('owner', self.DEFAULT_CONFIG.get('agents').get('owner')))
        package_dict['extras'].append({'key': 'holder_name', 'value': agent_name})
        package_dict['extras'].append({'key': 'holder_identifier', 'value': agent_code or default_ipa})

        # -----------------------------------------------#
        #    OTHER FIELDS NOT MANDATORY FOR DCAT_AP-IT   #
        # -----------------------------------------------#

        #  -- alternate_identifier nothing to do  -- #

        #  -- issued -- #
        publication_date = iso_values['date-released']
        package_dict['extras'].append({'key': 'issued', 'value': publication_date})

        #  -- geographical_name  -- #
        dataset_places = []
        if iso_values['keywords']:
            default_vocab_id = self.DEFAULT_CONFIG.get('controlled_vocabularies').get('dcatapit_skos_theme_id')
            dataset_places = utils.get_controlled_vocabulary_values(
                'places',
                controlled_vocabularies.get('dcatapit_skos_places_id', default_vocab_id), iso_values['keywords'])

        if dataset_places and len(dataset_places) > 1:
            dataset_places = list(set(dataset_places))
            dataset_places = '{' + ','.join(str(l) for l in dataset_places) + '}'
        else:
            dataset_places = dataset_places[0] if dataset_places and len(dataset_places) > 0 else \
                dcatapit_config.get('dataset_places',
                                    self.DEFAULT_CONFIG.get('dataset_places'))

        if dataset_places:
            log.info('Metadata harvested dataset places: %r', dataset_places)
            package_dict['extras'].append({'key': 'geographical_name', 'value': dataset_places})

        #  -- geographical_geonames_url nothing to do  -- #

        #  -- language -- #
        dataset_languages = iso_values['dataset-language']
        language = None
        if dataset_languages and len(dataset_languages) > 0:
            languages = []
            for language in dataset_languages:
                lang = mapping_languages_to_mdr_vocabulary.get(language, None)
                if lang:
                    languages.append(lang)

            if len(languages) > 1:
                language = '{' + ','.join(str(l) for l in languages) + '}'
            else:
                language = languages[0] if len(languages) > 0 else dcatapit_config.get('dataset_languages',
                                                                                       self.DEFAULT_CONFIG.get('dataset_languages'))

            log.info('Metadata harvested dataset languages: %r', language)
        else:
            language = dcatapit_config.get('dataset_language')

        package_dict['extras'].append({'key': 'language', 'value': language})

        # temporal_coverage
        # ##################
        temporal_coverage = []
        temporal_start = None
        temporal_end = None

        for key in ['temporal-extent-begin', 'temporal-extent-end']:
            if len(iso_values[key]) > 0:
                temporal_extent_value = iso_values[key][0]
                if key == 'temporal-extent-begin':
                    temporal_start = temporal_extent_value
                elif key == 'temporal-extent-end':
                    temporal_end = temporal_extent_value
        if temporal_start:
            temporal_coverage.append({'temporal_start': temporal_start,
                                      'temporal_end': temporal_end})
        if temporal_coverage:
            package_dict['extras'].append({'key': 'temporal_coverage', 'value': json.dumps(temporal_coverage)})

        # conforms_to
        # ##################
        conforms_to_identifier = iso_values['conformity-specification-title']
        conforms_to_locale = self._ckan_locales_mapping.get(iso_values['metadata-language'], 'it').lower()

        conforms_to = {'identifier': conforms_to_identifier,
                       'title': {conforms_to_locale: conforms_to_identifier}}

        if conforms_to:
            package_dict['extras'].append({'key': 'conforms_to', 'value': json.dumps([conforms_to])})

        # creator
        # ###############
        #  -- creator -- #
        agent_name, agent_code = utils.get_responsible_party(
            iso_values['cited-responsible-party'],
            agents.get('author', self.DEFAULT_CONFIG.get('agents').get('author')))

        agent_code = agent_code or default_ipa
        if agent_name and agent_code:
            creator = {}
            creator_lang = self._ckan_locales_mapping.get(iso_values['metadata-language'], 'it').lower()
            creator['creator_name'] = {creator_lang: agent_name}
            creator['creator_identifier'] = agent_code
            package_dict['extras'].append({'key': 'creator', 'value': json.dumps([creator])})

        # ckan_license
        # ##################
        ckan_license = None
        use_constraints = iso_values.get('use-constraints')
        if use_constraints:
            use_constraints = use_constraints[0]
            import ckan.logic.action.get as _license
            license_list = _license.license_list({'model': model, 'session': Session, 'user': 'harvest'}, {})
            for license in license_list:
                if use_constraints == str(license.get('id')) or \
                        use_constraints == str(license.get('url')) or \
                        (str(license.get('id')) in use_constraints.lower()):
                    ckan_license = license
                    break

        if ckan_license:
            package_dict['license_id'] = ckan_license.get('id')
        else:
            default_license = self.source_config.get('default_license')
            if default_license:
                package_dict['license_id'] = default_license

        #  -- license handling -- #
        interfaces.populate_resource_license(package_dict)

        # End of processing, return the modified package
        return package_dict
