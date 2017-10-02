import traceback, sys
""" Data model to represent biochemical models.

This module defines classes that represent the schema of a biochemical model:

* :obj:`Taxon`
* :obj:`Submodel`
* :obj:`ObjectiveFunction`
* :obj:`Compartment`
* :obj:`SpeciesType`
* :obj:`Species`
* :obj:`Concentration`
* :obj:`Reaction`
* :obj:`ReactionParticipant`
* :obj:`RateLaw`
* :obj:`RateLawEquation`
* :obj:`BiomassComponent`
* :obj:`BiomassReaction`
* :obj:`Parameter`
* :obj:`Reference`
* :obj:`CrossReference`

These are all instances of `BaseModel`, an alias for `obj_model.core.Model`.
A biochemical model may contain a list of instances of each of these classes, interlinked
by object references. For example, a :obj:`Reaction` will reference its constituent
:obj:`ReactionParticipant` instances, and the :obj:`RateLaw` that describes the reaction's rate.

This module also defines numerous classes that serve as attributes of these classes.

:Author: Jonathan Karr <karr@mssm.edu>
:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Date: 2016-11-10
:Copyright: 2016-2017, Karr Lab
:License: MIT
"""

# todo: replace py_expression.replace(...) with python tokenization, as in multialgorithm_simulation.py

from enum import Enum, EnumMeta
from itertools import chain
from math import ceil, floor, exp, log, log10, isnan
from natsort import natsorted, ns
from six import with_metaclass
from obj_model.core import (Model as BaseModel,
                            BooleanAttribute, EnumAttribute, FloatAttribute, IntegerAttribute, PositiveIntegerAttribute,
                            RegexAttribute, SlugAttribute, StringAttribute, LongStringAttribute, UrlAttribute,
                            OneToOneAttribute, ManyToOneAttribute, ManyToManyAttribute,
                            InvalidModel, InvalidObject, InvalidAttribute,
                            TabularOrientation)
import obj_model
from wc_utils.util.enumerate import CaseInsensitiveEnum, CaseInsensitiveEnumMeta
from wc_lang.sbml.util import (wrap_libsbml, str_to_xmlstr, LibSBMLError, init_sbml_model, create_sbml_parameter,
                                create_sbml_unit)
from libsbml import (XMLNode,)
import re
import sys

# wc_lang generates obj_model SchemaWarning warnings because some Models lack primary attributes.
# These models include RateLaw, ReactionParticipant, RateLawEquation, and Species.
# However, these are not needed by the workbook and delimiter-separated representations of
# models on disk. Therefore, suppress the warnings.
import warnings
warnings.filterwarnings('ignore', '', obj_model.core.SchemaWarning, 'obj_model.core')


class TaxonRankMeta(CaseInsensitiveEnumMeta):

    def __getattr__(cls, name):
        """ Get value by name

        Args:
            name (:obj:`str`): attribute name

        Returns:
            :obj:`TaxonRank`: taxonomic rank
        """
        if name.lower() == 'class':
            name = 'classis'
        return super(TaxonRankMeta, cls).__getattr__(name)

    def __getitem__(cls, name):
        """ Get value by name

        Args:
            name (:obj:`str`): attribute name

        Returns:
            :obj:`TaxonRank`: taxonomic rank
        """
        lower_name = name.lower()

        if lower_name in ['varietas', 'strain']:
            name = 'variety'
        elif lower_name == 'tribus':
            name = 'tribe'
        elif lower_name == 'familia':
            name = 'family'
        elif lower_name == 'ordo':
            name = 'order'
        elif lower_name == 'class':
            name = 'classis'
        elif lower_name in ['division', 'divisio']:
            name = 'phylum'
        elif lower_name == 'regnum':
            name = 'kingdom'
        return super(TaxonRankMeta, cls).__getitem__(name)


class TaxonRank(with_metaclass(TaxonRankMeta, int, Enum)):
    """ Taxonomic ranks """
    domain = 1
    kingdom = 2
    phylum = 3
    classis = 4
    order = 5
    family = 6
    tribe = 7
    genus = 8
    species = 9
    variety = 10


class SubmodelAlgorithm(int, CaseInsensitiveEnum):
    """ Submodel algorithms """
    dfba = 1
    ode = 2
    ssa = 3


class SpeciesTypeType(int, CaseInsensitiveEnum):
    """ Types of species types """
    metabolite = 1
    protein = 2
    rna = 3
    pseudo_species = 4


class RateLawDirection(int, CaseInsensitiveEnum):
    """ Rate law directions """
    backward = -1
    forward = 1


class ReferenceType(int, CaseInsensitiveEnum):
    """ Reference types """
    article = 1
    book = 2
    online = 3
    proceedings = 4
    thesis = 5

    inbook = 6
    incollection = 7
    inproceedings = 8

    misc = 9


class ObjectiveFunctionAttribute(OneToOneAttribute):
    """ Objective function attribute """

    def __init__(self, related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super(ObjectiveFunctionAttribute, self).__init__('ObjectiveFunction',
            related_name=related_name,
            verbose_name=verbose_name, verbose_related_name=verbose_related_name, help=help)

    def serialize(self, value):
        """ Serialize related object

        Args:
            value (:obj:`ObjectiveFunction`): the referenced ObjectiveFunction

        Returns:
            :obj:`str`: simple Python representation
        """
        if value is None:
            return None
        else:
            return value.serialize()

    def deserialize(self, value, objects):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        return ObjectiveFunction.deserialize(self, value, objects)


class OneToOneSpeciesAttribute(OneToOneAttribute):
    """ Species attribute """

    def __init__(self, related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super(OneToOneSpeciesAttribute, self).__init__('Species',
                                                       related_name=related_name, min_related=1, min_related_rev=0,
                                                       verbose_name=verbose_name, verbose_related_name=verbose_related_name, help=help)

    def serialize(self, value):
        """ Serialize related object

        Args:
            value (:obj:`Model`): Python representation

        Returns:
            :obj:`str`: simple Python representation
        """
        return value.serialize()

    def deserialize(self, value, objects):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model

        Returns:
            :obj:`tuple` of `list` of `ReactionParticipant`, `InvalidAttribute` or `None`: tuple of cleaned value
                and cleaning error
        """
        return Species.deserialize(self, value, objects)


class ReactionParticipantsAttribute(ManyToManyAttribute):
    """ Reaction participants """

    def __init__(self, related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super(ReactionParticipantsAttribute, self).__init__('ReactionParticipant', related_name=related_name,
                                                            verbose_name=verbose_name,
                                                            verbose_related_name=verbose_related_name,
                                                            help=help)

    def serialize(self, participants):
        """ Serialize related object

        Args:
            participants (:obj:`list` of `ReactionParticipant`): Python representation of reaction participants

        Returns:
            :obj:`str`: simple Python representation
        """
        if not participants:
            return ''

        comps = set([part.species.compartment for part in participants])
        if len(comps) == 1:
            global_comp = comps.pop()
        else:
            global_comp = None

        if global_comp:
            participants = natsorted(participants, lambda part: part.species.species_type.id, alg=ns.IGNORECASE)
        else:
            participants = natsorted(participants, lambda part: (
                part.species.species_type.id, part.species.compartment.id), alg=ns.IGNORECASE)

        lhs = []
        rhs = []
        for part in participants:
            if part.coefficient < 0:
                lhs.append(part.serialize(show_compartment=global_comp is None, show_coefficient_sign=False))
            elif part.coefficient > 0:
                rhs.append(part.serialize(show_compartment=global_comp is None, show_coefficient_sign=False))

        if global_comp:
            return '[{}]: {} ==> {}'.format(global_comp.get_primary_attribute(), ' + '.join(lhs), ' + '.join(rhs))
        else:
            return '{} ==> {}'.format(' + '.join(lhs), ' + '.join(rhs))

    def deserialize(self, value, objects):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model

        Returns:
            :obj:`tuple` of `list` of `ReactionParticipant`, `InvalidAttribute` or `None`: tuple of cleaned value
                and cleaning error
        """
        errors = []

        id = '[a-z][a-z0-9_]*'
        stoch = '\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\)'
        gbl_part = '({} )*({})'.format(stoch, id)
        lcl_part = '({} )*({}\[{}\])'.format(stoch, id, id)
        gbl_side = '{}( \+ {})*'.format(gbl_part, gbl_part)
        lcl_side = '{}( \+ {})*'.format(lcl_part, lcl_part)
        gbl_pattern = '^\[({})\]: ({}) ==> ({})$'.format(id, gbl_side, gbl_side)
        lcl_pattern = '^({}) ==> ({})$'.format(lcl_side, lcl_side)

        global_match = re.match(gbl_pattern, value, flags=re.I)
        local_match = re.match(lcl_pattern, value, flags=re.I)

        if global_match:
            if global_match.group(1) in objects[Compartment]:
                global_comp = objects[Compartment][global_match.group(1)]
            else:
                global_comp = None
                errors.append('Undefined compartment "{}"'.format(global_match.group(1)))
            lhs = global_match.group(2)
            rhs = global_match.group(14)

        elif local_match:
            global_comp = None
            lhs = local_match.group(1)
            rhs = local_match.group(13)

        else:
            return (None, InvalidAttribute(self, ['Incorrectly formatted participants: {}'.format(value)]))

        lhs_parts, lhs_errors = self.deserialize_side(-1., lhs, objects, global_comp)
        rhs_parts, rhs_errors = self.deserialize_side( 1., rhs, objects, global_comp)

        parts = lhs_parts + rhs_parts
        errors.extend(lhs_errors)
        errors.extend(rhs_errors)

        if errors:
            return (None, InvalidAttribute(self, errors))
        return (parts, None)

    def deserialize_side(self, direction, value, objects, global_comp):
        """ Deserialize the LHS or RHS of a reaction equation

        Args:
            direction (:obj:`float`): -1. indicates LHS, +1. indicates RHS
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            global_comp (:obj:`Compartment`): global compartment of the reaction

        Returns:
            :obj:`tuple`:

                * :obj:`list` of :obj:`ReactionParticipant`: list of reaction participants
                * :obj:`list` of :obj:`Exception`: list of errors
        """
        parts = []
        errors = []

        for part in re.findall('(\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\) )*([a-z][a-z0-9_]*)(\[([a-z][a-z0-9_]*)\])*', value, flags=re.I):
            part_errors = []

            if part[4] in objects[SpeciesType]:
                species_type = objects[SpeciesType][part[4]]
            else:
                part_errors.append('Undefined species type "{}"'.format(part[4]))

            if global_comp:
                compartment = global_comp
            elif part[6] in objects[Compartment]:
                compartment = objects[Compartment][part[6]]
            else:
                part_errors.append('Undefined compartment "{}"'.format(part[6]))

            coefficient = direction * float(part[1] or 1.)

            if part_errors:
                errors += part_errors
            else:
                spec_primary_attribute = '{}[{}]'.format(
                    species_type.get_primary_attribute(), compartment.get_primary_attribute())
                species, error = Species.deserialize(self, spec_primary_attribute, objects)
                if error:
                    raise ValueError('Invalid species "{}"'.format(spec_primary_attribute))

                if coefficient != 0:
                    if ReactionParticipant not in objects:
                        objects[ReactionParticipant] = {}
                    serialized_value = ReactionParticipant._serialize(species, coefficient)
                    if serialized_value in objects[ReactionParticipant]:
                        rxn_part = objects[ReactionParticipant][serialized_value]
                    else:
                        rxn_part = ReactionParticipant(species=species, coefficient=coefficient)
                        objects[ReactionParticipant][serialized_value] = rxn_part
                    parts.append(rxn_part)

        return (parts, errors)


class RateLawEquationAttribute(OneToOneAttribute):
    """ Rate law equation """

    def __init__(self, related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super(RateLawEquationAttribute, self).__init__('RateLawEquation',
                                                       related_name=related_name, min_related=1, min_related_rev=1,
                                                       verbose_name=verbose_name, verbose_related_name=verbose_related_name, help=help)

    def serialize(self, value):
        """ Serialize related object

        Args:
            value (:obj:`RateLawEquation`): the related RateLawEquation

        Returns:
            :obj:`str`: simple Python representation of the rate law equation
        """
        return value.serialize()

    def deserialize(self, value, objects):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        return RateLawEquation.deserialize(self, value, objects)


class Model(BaseModel):
    """ Model

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        version (:obj:`str`): version number
        wc_lang_version (:obj:`str`): wc_lang version number
        comments (:obj:`str`): comments

        cross_references (:obj:`list` of `CrossReference`): cross references
        taxon (:obj:`Taxon`): taxon
        submodels (:obj:`list` of `Submodel`): submodels
        compartments (:obj:`list` of `Compartment`): compartments
        species_types (:obj:`list` of `SpeciesType`): species types
        parameters (:obj:`list` of `Parameter`): parameters
        references (:obj:`list` of `Reference`): references
    """
    id = SlugAttribute()
    name = StringAttribute()
    version = RegexAttribute(min_length=1, pattern='^[0-9]+\.[0-9+]\.[0-9]+', flags=re.I)
    wc_lang_version = RegexAttribute(min_length=1, pattern='^[0-9]+\.[0-9+]\.[0-9]+', flags=re.I,
                                     verbose_name='wc_lang version')
    comments = LongStringAttribute()

    class Meta(BaseModel.Meta):
        attribute_order = ('id', 'name', 'version', 'wc_lang_version', 'comments')
        tabular_orientation = TabularOrientation.column

    def get_compartments(self):
        """ Get all compartments

        Returns:
            :obj:`list` of `Compartment`: compartments
        """
        return self.compartments

    def get_species_types(self):
        """ Get all species types

        Returns:
            :obj:`list` of `SpeciesType`: species types
        """
        return self.species_types

    def get_submodels(self):
        """ Get all submodels

        Returns:
            :obj:`list` of `Submodel`: submodels
        """
        return self.submodels

    def get_species(self):
        """ Get all species from submodels

        Returns:
            :obj:`list` of `Species`: species
        """
        species = []

        for submodel in self.submodels:
            species.extend(submodel.get_species())

        for concentation in self.get_concentrations():
            species.append(concentation.species)

        return list(set(species))

    def get_concentrations(self):
        """ Get all concentrations from species types

        Returns:
            :obj:`list` of `Concentration`: concentations
        """
        concentrations = []
        for species_type in self.species_types:
            for species in species_type.species:
                if species.concentration:
                    concentrations.append(species.concentration)
        return concentrations

    def get_reactions(self):
        """ Get all reactions from submodels

        Returns:
            :obj:`list` of `Reaction`: reactions
        """
        reactions = []
        for submodel in self.submodels:
            reactions.extend(submodel.reactions)
        return reactions

    def get_rate_laws(self):
        """ Get all rate laws from reactions

        Returns:
            :obj:`list` of `RateLaw`: rate laws
        """
        rate_laws = []
        for reaction in self.get_reactions():
            rate_laws.extend(reaction.rate_laws)
        return rate_laws

    def get_parameters(self):
        """ Get all parameters from model and submodels

        Returns:
            :obj:`list` of `Parameter`: parameters
        """
        parameters = []
        parameters.extend(self.parameters)
        for submodel in self.submodels:
            parameters.extend(submodel.parameters)
        return list(set(parameters))

    def get_references(self):
        """ Get all references from model and children

        Returns:
            :obj:`list` of `Reference`: references
        """
        refs = []

        refs.extend(self.references)

        if self.taxon:
            refs.extend(self.taxon.references)

        for compartment in self.compartments:
            refs.extend(compartment.references)

        for species_type in self.species_types:
            refs.extend(species_type.references)

        for concentration in self.get_concentrations():
            refs.extend(concentration.references)

        for submodel in self.submodels:
            refs.extend(submodel.references)

        for reaction in self.get_reactions():
            refs.extend(reaction.references)

        for rate_law in self.get_rate_laws():
            refs.extend(rate_law.references)

        for parameter in self.get_parameters():
            refs.extend(parameter.references)

        return list(set(refs))

    def get_component(self, type, id):
        """ Find model component of `type` with `id`

        Args:
            type (:obj:`str`) type of component to find
            id (:obj:`str`): id of component to find

        Returns:
            :obj:`BaseModel`: component with `id`, or `None` if there is no component with `id`=`id`
        """
        types = ['compartment', 'species_type', 'submodel', 'reaction', 'parameter', 'reference']
        if type not in types:
            raise ValueError('Type must be one of {}'.format(', '.join(types)))

        components = getattr(self, 'get_{}s'.format(type))()
        return next((c for c in components if c.id == id), None)


class Taxon(BaseModel):
    """ Biological taxon (e.g. family, genus, species, strain, etc.)

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        model (:obj:`Model`): model
        rank (:obj:`TaxonRank`): rank
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references

        cross_references (:obj:`list` of `CrossReference`): cross references
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = OneToOneAttribute('Model', related_name='taxon')
    rank = EnumAttribute(TaxonRank, default=TaxonRank.species)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='taxa')

    class Meta(BaseModel.Meta):
        attribute_order = ('id', 'name',
                           'model',
                           'rank',
                           'comments', 'references')
        tabular_orientation = TabularOrientation.column


class Submodel(BaseModel):
    """ Submodel

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        model (:obj:`Model`): model
        algorithm (:obj:`SubmodelAlgorithm`): algorithm
        compartment (:obj:`Compartment`): the compartment that contains the submodel's species
        biomass_reaction (:obj:`BiomassReaction`): the growth reaction for a dFBA submodel
        objective_function (:obj:`ObjectiveFunction`, optional): objective function for a dFBA submodel;
            if not provided, then `biomass_reaction` is used as the objective function
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references

        cross_references (:obj:`list` of `CrossReference`): cross references
        reactions (:obj:`list` of `Reaction`): reactions
        parameters (:obj:`list` of `Parameter`): parameters
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute('Model', related_name='submodels')
    algorithm = EnumAttribute(SubmodelAlgorithm, default=SubmodelAlgorithm.ssa)
    compartment = ManyToOneAttribute('Compartment', related_name='submodels')
    biomass_reaction = ManyToOneAttribute('BiomassReaction', related_name='submodels')
    objective_function = ObjectiveFunctionAttribute(related_name='submodel')
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='submodels')

    class Meta(BaseModel.Meta):
        attribute_order = ('id', 'name', 'model',
                           'algorithm', 'compartment', 'biomass_reaction',
                           'objective_function', 'comments', 'references')
        indexed_attrs_tuples = (('id',), )

    def get_species(self):
        """ Get species in reactions

        Returns:
            :obj:`list` of `Species`: species in reactions
        """
        species = []

        for rxn in self.reactions:
            species.extend(rxn.get_species())

        return list(set(species))

    def add_to_sbml_doc(self, sbml_document):
        """ Add this Submodel to a libsbml SBML document as a `libsbml.model`.

        Creates the document's `libsbml.model`.

        Args:
             sbml_document (:obj:`obj`): a `libsbml` SBMLDocument

        Returns:
            :obj:`libsbml.model`: the libsbml model that's created

        Raises:
            :obj:`LibSBMLError`: if calling `libsbml` raises an error
        """
        sbml_model = wrap_libsbml("sbml_document.getModel()")
        wrap_libsbml("sbml_model.setId(self.id)")
        wrap_libsbml("sbml_model.setName(self.name)")
        if self.comments:
            wrap_libsbml("sbml_model.appendNotes(str_to_xmlstr(self.comments))")
        return sbml_model


class ObjectiveFunction(BaseModel):
    """ Objective function

    Attributes:
        expression (:obj:`str`): input mathematical expression of the objective function
        reactions (:obj:`list` of `Reaction`): reactions whose fluxes are used in the objective function
        biomass_reactions (:obj:`list` of `BiomassReaction`): biomass reactions whose fluxes are used
            in the objective function

        submodel (:obj:`Submodel`): the `Submodel` which uses this `ObjectiveFunction`
    """
    expression = LongStringAttribute()
    reactions = ManyToManyAttribute('Reaction', related_name='objective_functions')
    biomass_reactions = ManyToManyAttribute('BiomassReaction', related_name='objective_functions')

    class Meta(BaseModel.Meta):
        """
        Attributes:
            valid_functions (:obj:`tuple` of `str`): tuple of names of functions that can be used in
            this `ObjectiveFunction`
        """
        attribute_order = ('expression', 'reactions', 'biomass_reactions')
        tabular_orientation = TabularOrientation.inline
        # objective functions must be continuous
        valid_functions = (exp, pow, log, log10)

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return self.expression

    @classmethod
    def deserialize(cls, attribute, value, objects):
        """ Deserialize value

        Args:
            attribute (:obj:`Attribute`): attribute
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of all `Model` objects, grouped by model

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        # if value is None don't create an ObjectiveFunction
        if value is None:
            return (None, None)

        # parse identifiers
        pattern = '(^|[^a-z0-9_])({})([^a-z0-9_]|$)'.format(SlugAttribute().pattern[1:-1])
        identifiers = []
        for match in re.findall(pattern, value, flags=re.I):
            identifiers.append(match[1])

        # allocate identifiers between reactions and biomass reactions
        reactions_dict = objects[Reaction]
        reaction_ids = reactions_dict.keys()
        reactions = []
        biomass_reactions_dict = objects[BiomassReaction]
        biomass_reaction_ids = biomass_reactions_dict.keys()
        biomass_reactions = []
        valid_functions_names = set(map(lambda f: f.__name__, cls.Meta.valid_functions))
        errors = []

        # do not allow Reaction or BiomassReaction instances with ids equal to a valid_function
        invalid_reaction_ids = valid_functions_names & set(reaction_ids) & set(identifiers)
        if invalid_reaction_ids:
            errors.append("reaction id(s) {{{}}} ambiguous between a Reaction and a "
                "valid function in '{}'".format(', '.join(list(invalid_reaction_ids)), value))
        invalid_biomass_reaction_ids = valid_functions_names & set(biomass_reaction_ids) & set(identifiers)
        if invalid_biomass_reaction_ids:
            errors.append("reaction id(s) {{{}}} ambiguous between a BiomassReaction "
                "and a valid function in '{}'".format(', '.join(list(invalid_biomass_reaction_ids)), value))

        for id in identifiers:

            if id in valid_functions_names:
                continue

            is_reaction = id in reaction_ids
            is_biomass_reactions = id in biomass_reaction_ids

            # redundant names
            if is_reaction and is_biomass_reactions:
                errors.append("id '{}' ambiguous between a Reaction and a "
                    "BiomassReaction in '{}'".format(id, value))

            # missing reaction
            if not (is_reaction or is_biomass_reactions):
                errors.append("id '{}' not a Reaction or a "
                    "BiomassReaction identifier in '{}'".format(id, value))

            if is_reaction:
                # a reaction may be used multiple times in an objective function
                if reactions_dict[id] not in reactions:
                    reactions.append(reactions_dict[id])

            if is_biomass_reactions:
                if biomass_reactions_dict[id] not in biomass_reactions:
                    biomass_reactions.append(biomass_reactions_dict[id])

        if errors:
            return (None, InvalidAttribute(attribute, errors, value=value))

        # create new ObjectiveFunction
        obj = cls(expression=value, reactions=reactions, biomass_reactions=biomass_reactions)
        if cls not in objects:
            objects[cls] = {}
        objects[cls][obj.serialize()] = obj
        return (obj, None)

    def validate(self):
        """ Determine whether an `ObjectiveFunction` is valid

        Returns:
            :obj:`InvalidObject` or None: `None` if the object is valid,
                otherwise return a list of errors in an `InvalidObject` instance
        """
        """ ensure that self.expression evaluates as valid Python """

        # to evaluate the expression, set variables for the reaction identifiers to their fluxes
        # test validation with fluxes of 1.0
        local_ns = {func.__name__: func for func in ObjectiveFunction.Meta.valid_functions}
        local_ns.update({rxn.id: 1.0 for rxn in self.reactions})
        local_ns.update({biomass_rxn.id: 1.0 for biomass_rxn in self.biomass_reactions})
        errors = []

        try:
            eval(self.expression, {}, local_ns)
        except SyntaxError as error:
            errors.append("syntax error in expression '{}'".format(self.expression))
        except NameError as error:
            errors.append("NameError in expression '{}'".format(self.expression))
        except Exception as error:
            errors.append("cannot eval expression '{}'".format(self.expression))

        if errors:
            attr = self.__class__.Meta.attributes['expression']
            attr_err = InvalidAttribute(attr, errors)
            return InvalidObject(self, [attr_err])

        """ return `None` to indicate valid object """
        return None


class Compartment(BaseModel):
    """ Compartment

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        model (:obj:`Model`): model
        initial_volume (:obj:`float`): initial volume (L)
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references

        cross_references (:obj:`list` of `CrossReference`): cross references
        concentrations (:obj:`list` of `Concentration`): concentrations
        reaction_participants (:obj:`list` of `ReactionParticipant`): reaction participants
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute('Model', related_name='compartments')
    initial_volume = FloatAttribute(min=0)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='compartments')

    class Meta(BaseModel.Meta):
        attribute_order = ('id', 'name',
                           'model',
                           'initial_volume',
                           'comments', 'references')

    def add_to_sbml_doc(self, sbml_document):
        """ Add this Compartment to a libsbml SBML document.

        Args:
             sbml_document (:obj:`obj`): a `libsbml` SBMLDocument

        Returns:
            :obj:`libsbml.compartment`: the libsbml compartment that's created

        Raises:
            :obj:`LibSBMLError`: if calling `libsbml` raises an error
        """
        sbml_model = wrap_libsbml("sbml_document.getModel()")
        sbml_compartment = wrap_libsbml("sbml_model.createCompartment()")
        wrap_libsbml("sbml_compartment.setId(self.id)")
        wrap_libsbml("sbml_compartment.setName(self.name)")
        wrap_libsbml("sbml_compartment.setSpatialDimensions(3)")
        wrap_libsbml("sbml_compartment.setSize(self.initial_volume)")
        if self.comments:
            wrap_libsbml("sbml_compartment.appendNotes(str_to_xmlstr(self.comments))")
        return sbml_compartment


class SpeciesType(BaseModel):
    """ Species type

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        model (:obj:`Model`): model
        structure (:obj:`str`): structure (InChI for metabolites; sequence for DNA, RNA, proteins)
        empirical_formula (:obj:`str`): empirical formula
        molecular_weight (:obj:`float`): molecular weight
        charge (:obj:`int`): charge
        type (:obj:`SpeciesTypeType`): type
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references

        cross_references (:obj:`list` of `CrossReference`): cross references
        concentrations (:obj:`list` of `Concentration`): concentrations
        reaction_participants (:obj:`list` of `ReactionParticipant`): reaction participants
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute('Model', related_name='species_types')
    structure = LongStringAttribute()
    empirical_formula = RegexAttribute(pattern='^([A-Z][a-z]?\d*)*$')
    molecular_weight = FloatAttribute(min=0)
    charge = IntegerAttribute()
    type = EnumAttribute(SpeciesTypeType, default=SpeciesTypeType.metabolite)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='species_types')

    class Meta(BaseModel.Meta):
        verbose_name = 'Species type'
        attribute_order = ('id', 'name',
                           'model',
                           'structure', 'empirical_formula', 'molecular_weight', 'charge', 'type',
                           'comments', 'references')
        indexed_attrs_tuples = (('id',), )

    # todo: move to compiled model
    def is_carbon_containing(self):
        """ Returns `True` is species contains at least one carbon atom.

        Returns:
            :obj:`bool`: `True` is species contains at least one carbon atom.
        """
        return re.match('C[1-9]', self.empirical_formula) is not None


class Species(BaseModel):
    """ Species (tuple of species type, compartment)

    Attributes:
        species_type (:obj:`SpeciesType`): species type
        compartment (:obj:`Compartment`): compartment

        concentration (:obj:`Concentration`): concentration
        reaction_participants (:obj:`list` of `Reaction`): participations in reactions
        rate_law_equations (:obj:`RateLawEquation`): rate law equations
    """
    species_type = ManyToOneAttribute('SpeciesType', related_name='species', min_related=1)
    compartment = ManyToOneAttribute('Compartment', related_name='species', min_related=1)

    class Meta(BaseModel.Meta):
        attribute_order = ('species_type', 'compartment')
        frozen_columns = 1
        tabular_orientation = TabularOrientation.inline
        unique_together = (('species_type', 'compartment', ), )
        ordering = ('species_type', 'compartment')

    def id(self):
        """ Provide a Species' primary identifier

        Returns:
            :obj:`str`: canonical identifier for a specie in a compartment, 'specie_id[compartment_id]'
        """
        return self.serialize()

    def serialize(self):
        """ Provide a Species' primary identifier

        Returns:
            :obj:`str`: canonical identifier for a specie in a compartment, 'specie_id[compartment_id]'
        """
        return '{}[{}]'.format(
            self.species_type.get_primary_attribute(),
            self.compartment.get_primary_attribute())

    @staticmethod
    def get(ids, species_iterator):
        """ Find some Species instances

        Args:
            ids (:obj:`Iterator` of `str`): an iterator over some species identifiers
            species_iterator (:obj:`Iterator`): an iterator over some species

        Returns:
            :obj:`list` of `Species` or `None`: each element of the `list` corresponds to an element
                of `ids` and contains either a `Species` with `id()` equal to the element in `ids`,
                or `None` indicating that `species_iterator` does not contain a matching `Species`
        """
        # TODO: this costs O(|ids||species_iterator|); replace with O(|ids|) operation using obj_model.Manager.get()
        rv = []
        for id in ids:
            s = None
            for specie in species_iterator:
                if specie.id() == id:
                    s = specie
                    # one match is enough
                    break
            rv.append(s)
        return rv

    @classmethod
    def deserialize(cls, attribute, value, objects):
        """ Deserialize value

        Args:
            attribute (:obj:`Attribute`): attribute
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        if cls in objects and value in objects[cls]:
            return (objects[cls][value], None)

        match = re.match('^([a-z][a-z0-9_]*)\[([a-z][a-z0-9_]*)\]$', value, flags=re.I)
        if match:
            errors = []

            if match.group(1) in objects[SpeciesType]:
                species_type = objects[SpeciesType][match.group(1)]
            else:
                errors.append('Species type "{}" is not defined'.format(match.group(1)))

            if match.group(2) in objects[Compartment]:
                compartment = objects[Compartment][match.group(2)]
            else:
                errors.append('Compartment "{}" is not defined'.format(match.group(2)))

            if errors:
                return (None, InvalidAttribute(attribute, errors))
            else:
                obj = cls(species_type=species_type, compartment=compartment)
                if cls not in objects:
                    objects[cls] = {}
                objects[cls][obj.serialize()] = obj
                return (obj, None)

        return (None, InvalidAttribute(attribute, ['Invalid species']))

    def xml_id(self):
        """ Make a Species id that satisfies the SBML string id syntax.

        Replaces the '[' and ']' in Species.id() with double-underscores '__'.
        See Finney and Hucka, "Systems Biology Markup Language (SBML) Level 2: Structures and
        Facilities for Model Definitions", 2003, section 3.4.

        Returns:
            :obj:`str`: an SBML id
        """
        return '{}__{}__'.format(
            self.species_type.get_primary_attribute(),
            self.compartment.get_primary_attribute())

    def add_to_sbml_doc(self, sbml_document):
        """ Add this Species to a libsbml SBML document.

        Args:
             sbml_document (:obj:`obj`): a `libsbml` SBMLDocument

        Returns:
            :obj:`libsbml.species`: the libsbml species that's created

        Raises:
            :obj:`LibSBMLError`: if calling `libsbml` raises an error
        """
        sbml_model = wrap_libsbml("sbml_document.getModel()")
        sbml_species = wrap_libsbml("sbml_model.createSpecies()")
        wrap_libsbml("sbml_species.setId(self.xml_id())")

        # add some SpeciesType data
        wrap_libsbml("sbml_species.setName(self.species_type.name)")
        if self.species_type.comments:
            wrap_libsbml("sbml_species.appendNotes(str_to_xmlstr(self.species_type.comments))")

        # set Compartment, which must already be in the SBML document
        wrap_libsbml("sbml_species.setCompartment(self.compartment.id)")

        # set the Initial Concentration
        wrap_libsbml("sbml_species.setInitialConcentration(self.concentration.value)")

        return sbml_species


class Concentration(BaseModel):
    """ Species concentration

    Attributes:
        species (:obj:`Species`): species
        value (:obj:`float`): value (M)
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references
    """
    species = OneToOneSpeciesAttribute(related_name='concentration')
    value = FloatAttribute(min=0)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='concentrations')

    class Meta(BaseModel.Meta):
        unique_together = (('species', ), )
        attribute_order = ('species',
                           'value',
                           'comments', 'references')
        frozen_columns = 1
        ordering = ('species',)

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return self.species.serialize()


class Reaction(BaseModel):
    """ Reaction

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        submodel (:obj:`Submodel`): submodel that reaction belongs to
        participants (:obj:`list` of `ReactionParticipant`): participants
        reversible (:obj:`bool`): indicates if reaction is thermodynamically reversible
        min_flux (:obj:`float`): minimum flux bound for solving an FBA model; negative for reversible reactions
        max_flux (:obj:`float`): maximum flux bound for solving an FBA model
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references

        cross_references (:obj:`list` of `CrossReference`): cross references
        rate_laws (:obj:`list` of `RateLaw`): rate laws
    """
    id = SlugAttribute()
    name = StringAttribute()
    submodel = ManyToOneAttribute('Submodel', related_name='reactions')
    participants = ReactionParticipantsAttribute(related_name='reactions')
    reversible = BooleanAttribute()
    min_flux = FloatAttribute(nan=True)
    max_flux = FloatAttribute(min=0, nan=True)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='reactions')

    class Meta(BaseModel.Meta):
        attribute_order = ('id', 'name',
                           'submodel',
                           'participants', 'reversible',
                           'min_flux', 'max_flux',
                           'comments', 'references')
        indexed_attrs_tuples = (('id',), )

    def get_species(self):
        """ Get species

        Returns:
            :obj:`list`: list of `Species`
        """
        species = []

        for part in self.participants:
            species.append(part.species)

        for rate_law in self.rate_laws:
            species.extend(rate_law.equation.modifiers)

        return list(set(species))

    def add_to_sbml_doc(self, sbml_document):
        """ Add this Reaction to a libsbml SBML document.

        Args:
             sbml_document (:obj:`obj`): a `libsbml` SBMLDocument

        Returns:
            :obj:`libsbml.reaction`: the libsbml reaction that's created

        Raises:
            :obj:`LibSBMLError`: if calling `libsbml` raises an error
        """
        sbml_model = wrap_libsbml("sbml_document.getModel()")

        # create SBML reaction in SBML document
        sbml_reaction = wrap_libsbml("sbml_model.createReaction()")
        wrap_libsbml("sbml_reaction.setId(self.id)")
        wrap_libsbml("sbml_reaction.setName(self.name)")
        wrap_libsbml("sbml_reaction.setCompartment(self.submodel.compartment.id)")
        if self.comments:
            wrap_libsbml("sbml_reaction.appendNotes(str_to_xmlstr(self.comments))")

        # write reaction participants to SBML document
        for participant in self.participants:
            if participant.coefficient<0:
                species_reference = wrap_libsbml("sbml_reaction.createReactant()")
                wrap_libsbml("species_reference.setStoichiometry(-participant.coefficient)")
            elif 0<participant.coefficient:
                species_reference = wrap_libsbml("sbml_reaction.createProduct()")
                wrap_libsbml("species_reference.setStoichiometry(participant.coefficient)")
            else:
                raise ValueError('coefficient is 0 for participant {} in reaction {}'.format(
                    participant.coefficient, self.id))
            wrap_libsbml("species_reference.setSpecies(participant.species.xml_id())")

        # write flux bounds to SBML document; uses version 2 of the 'Flux Balance Constraints' extension
        fbc_reaction_plugin = wrap_libsbml("sbml_reaction.getPlugin('fbc')")
        for bound in ['lower', 'upper']:
            # make a unique ID for each flux bound parameter
            param_id = "_reaction_{}_{}_bound".format(self.id, bound)
            param = create_sbml_parameter(sbml_model, id=param_id, units='mmol_per_gDW_per_hr',
                value=self.min_flux)
            if bound == 'lower':
                wrap_libsbml("param.setValue({})".format(self.min_flux))
                wrap_libsbml("fbc_reaction_plugin.setLowerFluxBound('{}')".format(param_id))
            if bound == 'upper':
                wrap_libsbml("param.setValue({})".format(self.max_flux))
                wrap_libsbml("fbc_reaction_plugin.setUpperFluxBound('{}')".format(param_id))
        return sbml_reaction


class ReactionParticipant(BaseModel):
    """ Species in a reaction

    Attributes:
        species (:obj:`Species`): species
        coefficient (:obj:`float`): coefficient

        reaction (:obj:`Reaction`): reaction
    """
    species = ManyToOneAttribute('Species', related_name='reaction_participants')
    coefficient = FloatAttribute(nan=False)

    class Meta(BaseModel.Meta):
        unique_together = (('species', 'coefficient'), )
        attribute_order = ('species', 'coefficient')
        frozen_columns = 1
        tabular_orientation = TabularOrientation.inline
        ordering = ('species',)

    def serialize(self, show_compartment=True, show_coefficient_sign=True):
        """ Serialize related object

        Args:
            show_compartment (:obj:`bool`, optional): if true, show compartment
            show_coefficient_sign (:obj:`bool`, optional): if true, show coefficient sign

        Returns:
            :obj:`str`: simple Python representation
        """
        return self._serialize(self.species, self.coefficient, 
            show_compartment=show_compartment, show_coefficient_sign=show_coefficient_sign)

    @staticmethod
    def _serialize(species, coefficient, show_compartment=True, show_coefficient_sign=True):
        """ Serialize values

        Args:
            species (:obj:`Species`): species
            coefficient (:obj:`float`): coefficient
            show_compartment (:obj:`bool`, optional): if true, show compartment
            show_coefficient_sign (:obj:`bool`, optional): if true, show coefficient sign

        Returns:
            :obj:`str`: simple Python representation
        """
        coefficient = float(coefficient)

        if not show_coefficient_sign:
            coefficient = abs(coefficient)

        if coefficient == 1:
            coefficient_str = ''
        elif coefficient % 1 == 0 and abs(coefficient) < 1000:
            coefficient_str = '({:.0f}) '.format(coefficient)
        else:
            coefficient_str = '({:e}) '.format(coefficient)

        if show_compartment:
            return '{}{}'.format(coefficient_str, species.serialize())
        else:
            return '{}{}'.format(coefficient_str, species.species_type.get_primary_attribute())

    @classmethod
    def deserialize(cls, attribute, value, objects, compartment=None):
        """ Deserialize value

        Args:
            attribute (:obj:`Attribute`): attribute
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            compartment (:obj:`Compartment`, optional): compartment

        Returns:
            :obj:`tuple` of `list` of `ReactionParticipant`, `InvalidAttribute` or `None`: tuple of cleaned value
                and cleaning error
        """
        errors = []

        if compartment:
            pattern = '^(\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\) )*([a-z][a-z0-9_]*)$'
        else:
            pattern = '^(\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\) )*([a-z][a-z0-9_]*\[[a-z][a-z0-9_]*\])$'

        match = re.match(pattern, value, flags=re.I)
        if match:
            errors = []

            coefficient = float(match.group(2) or 1.)

            if compartment:
                species_id = '{}[{}]'.format(match.group(5), compartment.get_primary_attribute())
            else:
                species_id = match.group(5)

            species, error = Species.deserialize(attribute, species_id, objects)
            if error:
                return error

            serial_val = cls._serialize(species, coefficient)
            if cls in objects and serial_val in objects[cls]:
                return (objects[cls][serial_val], None)

            obj = cls(species=species, coefficient=coefficient)
            if cls not in objects:
                objects[cls] = {}
            objects[cls][obj.serialize()] = obj
            return (obj, None)

        else:
            attr = cls.Meta.attributes['species']
            return (None, InvalidAttribute(attr, ['Invalid reaction participant']))


class RateLaw(BaseModel):
    """ Rate law

    Attributes:
        reaction (:obj:`Reaction`): reaction
        direction (:obj:`RateLawDirection`): direction
        equation (:obj:`RateLawEquation`): equation
        k_cat (:obj:`float`): v_max (reactions enz^-1 s^-1)
        k_m (:obj:`float`): k_m (M)
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references
    """

    reaction = ManyToOneAttribute('Reaction', related_name='rate_laws')
    direction = EnumAttribute(RateLawDirection, default=RateLawDirection.forward)
    equation = RateLawEquationAttribute(related_name='rate_law')
    k_cat = FloatAttribute(min=0, nan=True)
    k_m = FloatAttribute(min=0, nan=True)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='rate_laws')

    class Meta(BaseModel.Meta):
        attribute_order = ('reaction', 'direction',
                           'equation', 'k_cat', 'k_m',
                           'comments', 'references')
        unique_together = (('reaction', 'direction'), )
        ordering = ('reaction', 'direction',)

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return '{}.{}'.format(self.reaction.serialize(), self.direction.name)


class RateLawEquation(BaseModel):
    """ Rate law equation

    Attributes:
        expression (:obj:`str`): mathematical expression of the rate law
        transcoded (:obj:`str`): transcoded expression, suitable for evaluating as a Python expression
        modifiers (:obj:`list` of `Species`): species whose concentrations are used in the rate law

        rate_law (:obj:`RateLaw`): the `RateLaw` which uses this `RateLawEquation`
    """
    expression = LongStringAttribute()
    transcoded = LongStringAttribute()
    modifiers = ManyToManyAttribute('Species', related_name='rate_law_equations')

    class Meta(BaseModel.Meta):
        """
        Attributes:
            valid_functions (:obj:`tuple` of `str`): tuple of names of functions that can be used in this `RateLawEquation`
        """
        attribute_order = ('expression', 'modifiers')
        tabular_orientation = TabularOrientation.inline
        valid_functions = (ceil, floor, exp, pow, log, log10, min, max)
        ordering = ('rate_law',)

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return self.expression

    @classmethod
    def deserialize(cls, attribute, value, objects):
        """ Deserialize value

        Args:
            attribute (:obj:`Attribute`): attribute
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        modifiers = []
        errors = []
        pattern = '(^|[^a-z0-9_])({}\[{}\])([^a-z0-9_]|$)'.format(SpeciesType.id.pattern[1:-1],
                                                                  Compartment.id.pattern[1:-1])

        try:
            for match in re.findall(pattern, value, flags=re.I):
                species, error = Species.deserialize(attribute, match[1], objects)
                if error:
                    errors += error.messages
                else:
                    modifiers.append(species)
        except Exception as e:
            errors += ["deserialize fails on '{}'".format(value)]

        if errors:
            attr = cls.Meta.attributes['expression']
            return (None, InvalidAttribute(attribute, errors))

        # return value
        obj = cls(expression=value, modifiers=list(set(modifiers)))
        if cls not in objects:
            objects[cls] = {}
        objects[cls][obj.serialize()] = obj
        return (obj, None)

    def validate(self):
        """ Determine whether a `RateLawEquation` is valid

        Returns:
            :obj:`InvalidObject` or None: `None` if the object is valid,
                otherwise return a list of errors in an `InvalidObject` instance
        """

        pattern = '(^|[^a-z0-9_])({}\[{}\])([^a-z0-9_]|$)'.format(SpeciesType.id.pattern[1:-1],
                                                                  Compartment.id.pattern[1:-1])

        """ check that all named entities are defined """
        modifier_ids = set((x.serialize() for x in self.modifiers))
        species_ids = set([x[1] for x in re.findall(pattern, self.expression, flags=re.I)])

        if modifier_ids != species_ids:
            errors = []

            for id in modifier_ids.difference(species_ids):
                errors.append('Extraneous modifier "{}"'.format(id))

            for id in species_ids.difference(modifier_ids):
                errors.append('Undefined modifier "{}"'.format(id))

            attr = self.__class__.Meta.attributes['expression']
            attr_err = InvalidAttribute(attr, errors)
            return InvalidObject(self, [attr_err])

        """ Check that rate law evaluates """
        # setup name space and format expression for python evaluation
        local_ns = {f.__name__: f for f in self.__class__.Meta.valid_functions}

        if self.rate_law:
            if not isnan(self.rate_law.k_cat):
                local_ns['k_cat'] = self.rate_law.k_cat

            if not isnan(self.rate_law.k_m):
                local_ns['k_m'] = self.rate_law.k_m

        local_ns['s'] = []
        py_expression = self.expression
        for i_species, species_id in enumerate(set([x[1] for x in re.findall(pattern, self.expression, flags=re.I)])):
            local_ns['s'].append(1.)
            # warning: if a specie name matches the suffix of another this string replace may fail
            py_expression = py_expression.replace(species_id, 's[{}]'.format(i_species))

        # try evaluating law
        try:
            eval(py_expression, {'__builtins__': None}, local_ns)
        # todo: distinguish between SyntaxError, NameError, and other exceptions
        except Exception as error:
            msg = 'Invalid function: {}\n  {}'.format(self.expression, str(error).replace('\n', '\n  '))
            attr = self.__class__.Meta.attributes['expression']
            attr_err = InvalidAttribute(attr, [msg])
            return InvalidObject(self, [attr_err])

        """ return `None` to indicate valid object """
        return None


class BiomassComponent(BaseModel):
    """ BiomassComponent

    A biomass reaction contains a list of BiomassComponent instances. Distinct BiomassComponents
    enable separate comments and references for each one.

    Attributes:
        id (:obj:`str`): unique identifier per BiomassComponent
        name (:obj:`str`): name
        biomass_reaction (:obj:`BiomassReaction`): the biomass reaction that uses the biomass component
        coefficient (:obj:`float`): the specie's reaction coefficient
        species_type (:obj:`SpeciesType`): the specie type
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references
    """
    id = SlugAttribute()
    name = StringAttribute()
    biomass_reaction = ManyToOneAttribute('BiomassReaction', related_name='biomass_components')
    coefficient = FloatAttribute()
    species_type = ManyToOneAttribute('SpeciesType', related_name='biomass_components')
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='biomass_components')

    class Meta(BaseModel.Meta):
        unique_together = (('biomass_reaction', 'species_type'), )
        attribute_order = ('id', 'name', 'biomass_reaction',
                           'coefficient', 'species_type',
                           'comments', 'references')


class BiomassReaction(BaseModel):
    """ BiomassReaction

    A pseudo-reaction used to estimate a cell's growth.

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references

        submodels (:obj:`Submodel`): the submodel that uses this biomass reaction
        biomass_components (:obj:`list` of `BiomassComponent`): the components of this biomass reaction
    """
    id = SlugAttribute()
    name = StringAttribute()
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='biomass_reactions')

    class Meta(BaseModel.Meta):
        attribute_order = ('id', 'name', 'comments', 'references')
        indexed_attrs_tuples = (('id',), )


class Parameter(BaseModel):
    """ Parameter

    Attributes:
        id (:obj:`str`): unique identifier per model/submodel
        name (:obj:`str`): name
        model (:obj:`Model`): model
        submodel (:obj:`Submodel`): submodel
        value (:obj:`float`): value
        units (:obj:`str`): units of value
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references
    """
    id = SlugAttribute(unique=False)
    name = StringAttribute()
    model = ManyToOneAttribute('Model', related_name='parameters')
    submodels = ManyToManyAttribute('Submodel', related_name='parameters')
    value = FloatAttribute(min=0)
    units = StringAttribute()
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='parameters')

    class Meta(BaseModel.Meta):
        unique_together = (('id', 'model', 'submodels', ), )
        attribute_order = ('id', 'name',
                           'model', 'submodels',
                           'value', 'units',
                           'comments', 'references')


class Reference(BaseModel):
    """ Reference

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        model (:obj:`Model`): model
        title (:obj:`str`): title
        author (:obj:`str`): author(s)
        editor (:obj:`str`): editor(s)
        year (:obj:`int`): year
        type (:obj:`ReferenceType`): type
        publication (:obj:`str`): publication title
        publisher (:obj:`str`): publisher
        series (:obj:`str`): series
        volume (:obj:`str`): volume
        number (:obj:`str`): number
        issue (:obj:`str`): issue
        edition (:obj:`str`): edition
        chapter (:obj:`str`): chapter
        pages (:obj:`str`): page range
        comments (:obj:`str`): comments

        cross_references (:obj:`list` of `CrossReference`): cross references
        taxa (:obj:`list` of `Taxon`): taxa
        submodels (:obj:`list` of `Submodel`): submodels
        compartments (:obj:`list` of `Compartment`): compartments
        species_types (:obj:`list` of `SpeciesType`): species types
        concentrations (:obj:`list` of `Concentration`): concentrations
        reactions (:obj:`list` of `Reaction`): reactions
        rate_laws (:obj:`list` of `RateLaw`): rate laws
        parameters (:obj:`list` of `Parameter`): parameters
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute('Model', related_name='references')
    title = StringAttribute()
    author = StringAttribute()
    editor = StringAttribute()
    year = PositiveIntegerAttribute()
    type = EnumAttribute(ReferenceType)
    publication = StringAttribute()
    publisher = StringAttribute()
    series = StringAttribute()
    volume = StringAttribute()
    number = StringAttribute()
    issue = StringAttribute()
    edition = StringAttribute()
    chapter = StringAttribute()
    pages = StringAttribute()
    comments = LongStringAttribute()

    class Meta(BaseModel.Meta):
        attribute_order = ('id', 'name', 'model',
                           'title', 'author', 'editor', 'year', 'type', 'publication', 'publisher',
                           'series', 'volume', 'number', 'issue', 'edition', 'chapter', 'pages',
                           'comments')


class CrossReference(BaseModel):
    """ Cross reference to a database

    Attributes:
        database (:obj:`str`): database name
        id (:obj:`str`): id of database entry
        url (:obj:`str`): URL of database entry
        model (:obj:`Model`): model
        taxon (:obj:`Taxon`): taxon
        submodel (:obj:`Submodel`): submodel
        species_type (:obj:`SpeciesType`): species type
        reaction (:obj:`Reaction`): reaction
        reference (:obj:`Reference`): reference
    """

    database = StringAttribute(min_length=1)
    id = StringAttribute(verbose_name='ID', min_length=1)
    url = UrlAttribute()
    model = ManyToOneAttribute('Model', related_name='cross_references')
    taxon = ManyToOneAttribute('Taxon', related_name='cross_references')
    submodel = ManyToOneAttribute('Submodel', related_name='cross_references')
    compartment = ManyToOneAttribute('Compartment', related_name='cross_references')
    species_type = ManyToOneAttribute('SpeciesType', related_name='cross_references')
    reaction = ManyToOneAttribute('Reaction', related_name='cross_references')
    reference = ManyToOneAttribute('Reference', related_name='cross_references')

    class Meta(BaseModel.Meta):
        unique_together = (('database', 'id', ), )
        attribute_order = ('database', 'id', 'url',
                           'model', 'taxon', 'submodel', 'compartment', 'species_type', 'reaction', 'reference')
        frozen_columns = 2
        ordering = ('database', 'id', )

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return '{}: {}'.format(self.database, self.id)
