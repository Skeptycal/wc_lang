""" Prepare a WC model for further processing, such as export or simulation.

:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Author: Jonathan Karr <jonrkarr@gmail.com>
:Date: 2018-11-26
:Copyright: 2017-2018, Karr Lab
:License: MIT
"""

from math import isnan
from obj_model.utils import get_component_by_id
from warnings import warn
from wc_lang.core import (SubmodelAlgorithm, Concentration, ConcentrationUnit)
import ast

# configuration
import wc_lang.config.core
config_wc_lang = wc_lang.config.core.get_config()['wc_lang']

EXTRACELLULAR_COMPARTMENT_ID = config_wc_lang['EXTRACELLULAR_COMPARTMENT_ID']


class PrepareModel(object):
    """ Statically prepare a model

    `Models` which validate usually lack data needed to use them. `PrepareModel` automates
    the addition of default and statically computed data to a `Model`.

    Currently added data:

        * Missing concentrations
        * Create implicit exchange reactions for dFBA submodels
        * Ensure that dFBA submodels have objective functions
        * Apply default flux bounds to the reactions in dFBA submodels
    """

    def __init__(self, model):
        self.model = model

    def run(self):
        """ Statically prepare a model by executing all `Prepare` methods.
        """
        self.init_concentrations()

        for submodel in self.model.get_submodels():
            if submodel.algorithm == SubmodelAlgorithm.dfba:
                reactions_created = self.create_dfba_exchange_rxns(submodel,
                                                                   EXTRACELLULAR_COMPARTMENT_ID)
                warn("{} exchange reactions created for submodel '{}'.".format(reactions_created,
                                                                               submodel.name))
                (min_bounds_set, max_bounds_set) = self.apply_default_dfba_submodel_flux_bounds(submodel)
                warn("{} minimum and {} maximum default flux bounds set for submodel '{}'.".format(
                    min_bounds_set, max_bounds_set, submodel.name))
                try:
                    reactions, biomass_reactions = self.parse_dfba_submodel_obj_func(submodel)
                    self.assign_linear_objective_fn(submodel, reactions, biomass_reactions)
                    submodel.dfba_obj.expression.linear = True
                except Exception as e:
                    submodel.dfba_obj.expression.linear = False
                    warn("Submodel '{}' has non-linear objective function '{}'.".format(
                        submodel.name, submodel.dfba_obj.expression.expression))

    def create_dfba_exchange_rxns(self, submodel, extracellular_compartment_id):
        """ Create exchange reactions for a dFBA submodel's reaction network.

        To represent FBA's mathematical assumption that it models a closed system, create
        'implicit' forward exchange reactions that synthesize all extracellular metabolites.

        # TODO: To model how other pathways consume metabolites generated by metabolism, create 'implicit'
        reactions which exchange these metabolites between a dFBA metabolism submodel and the other
        pathway(s)/submodel(s).

        Algorithm to synthesize extracellular metabolites::

            E = the set of all extracellular metabolites used by the submodel
            generate a "-> e" reaction for each e in E in the submodel

        Args:
            submodel (`Submodel`): a DFBA submodel
            extracellular_compartment_id (`str`): the id of the extracellular compartment

        Raises:
            ValueError: if `submodel` is not a dFBA submodel

        Returns:
            :obj:`int`: the number of reactions created
        """
        if submodel.algorithm != SubmodelAlgorithm.dfba:
            raise ValueError("submodel '{}' not a dFBA submodel".format(submodel.name))

        reaction_number = 1

        for specie in submodel.get_species():
            if specie.compartment.id == extracellular_compartment_id:

                EXCHANGE_RXN_ID_PREFIX = config_wc_lang['EXCHANGE_RXN_ID_PREFIX']
                EXCHANGE_RXN_NAME_PREFIX = config_wc_lang['EXCHANGE_RXN_NAME_PREFIX']
                # generate a "-> specie" reaction
                new_rxn = submodel.reactions.create(
                    id="{}_{}".format(EXCHANGE_RXN_ID_PREFIX, reaction_number),
                    name="{}_{}".format(EXCHANGE_RXN_NAME_PREFIX, reaction_number),
                    reversible=False,
                    min_flux=-float('inf'),
                    max_flux=float('inf'))
                reaction_number += 1
                new_rxn.participants.create(species=specie, coefficient=1)

        return reaction_number-1

    def apply_default_dfba_submodel_flux_bounds(self, submodel):
        """ Apply default flux bounds to a dFBA submodel's reactions

        The FBA optimizer needs min and max flux bounds for each dFBA submodel reaction.
        If some reactions lack bounds and default bounds are provided in a config file,
        then apply the defaults to the reactions.
        Specifically, min and max default bounds are applied as follows:

            reversible reactions:

              * min_flux = -default_max_flux_bound
              * max_flux = default_max_flux_bound

            irreversible reactions:

              * min_flux = default_min_flux_bound
              * max_flux = default_max_flux_bound

        Args:
            submodel (:obj:`Submodel`): a dFBA submodel

        Raises:
            ValueError: if `submodel` is not a dFBA submodel

        Returns:
            :obj:`tuple`:

                * obj:`int`: number of min flux bounds set to the default
                * obj:`int`: number of max flux bounds set to the default
        """
        if submodel.algorithm != SubmodelAlgorithm.dfba:
            raise ValueError("submodel '{}' not a dFBA submodel".format(submodel.name))

        need_default_flux_bounds = False
        for rxn in submodel.reactions:
            need_default_flux_bounds = need_default_flux_bounds or isnan(rxn.min_flux) or isnan(rxn.max_flux)
        if not need_default_flux_bounds:
            # all reactions have flux bounds
            return (0, 0)

        # Are default flux bounds available? They cannot be negative.
        try:
            default_min_flux_bound = config_wc_lang['default_min_flux_bound']
            default_max_flux_bound = config_wc_lang['default_max_flux_bound']
        except KeyError as e:
            raise ValueError("cannot obtain default_min_flux_bound and default_max_flux_bound=")
        if not 0 <= default_min_flux_bound <= default_max_flux_bound:
            raise ValueError("default flux bounds violate 0 <= default_min_flux_bound <= default_max_flux_bound:\n"
                             "default_min_flux_bound={}; default_max_flux_bound={}".format(default_min_flux_bound,
                                                                                           default_max_flux_bound))

        # Apply default flux bounds to reactions in submodel
        num_default_min_flux_bounds = 0
        num_default_max_flux_bounds = 0
        for rxn in submodel.reactions:
            if isnan(rxn.min_flux):
                num_default_min_flux_bounds += 1
                if rxn.reversible:
                    rxn.min_flux = -default_max_flux_bound
                else:
                    rxn.min_flux = default_min_flux_bound
            if isnan(rxn.max_flux):
                num_default_max_flux_bounds += 1
                rxn.max_flux = default_max_flux_bound
        return (num_default_min_flux_bounds, num_default_max_flux_bounds)

    def init_concentrations(self):
        """ Initialize missing concentration values to 0 """
        missing_species_ids = []
        for species in self.model.get_species():
            if species.concentration is None:
                missing_species_ids.append(species.id)
                species.concentrations = Concentration(
                    id=Concentration.gen_id(species.id),
                    species=species,
                    value=0.0, units=ConcentrationUnit.molecules)
        warn("Assuming missing concentrations for the following metabolites 0:\n  {}".format(
            '\n  '.join(missing_species_ids)))

    def parse_dfba_submodel_obj_func(self, submodel):
        """ Parse a dFBA submodel's objective function into a linear function of reaction fluxes

        The SBML FBC only handles objectives that are a linear function of reaction fluxes. This method
        uses Python's parser to parse an objective function.

        The general form for an objective is :math:`c_1*id_1 + c_2*id_2 + ... + c_n*id_n`,
        where :math:`c_i` is a numerical coefficient and :math:`id_i` is a reaction id. The ids may
        represent reactions or biomass reactions.
        Coefficients may also appear after an id, as in :math:`id_j*c_j`. Coefficients equal to 1.0
        are not needed. And negative coefficients are supported.

        Args:
            submodel (`Submodel`): a dFBA submodel

        Returns:
            :obj:`tuple`: a pair of lists representing the objective's linear form

                * obj:`list`: (coeff, id) pairs for reactions
                * obj:`list`: (coeff, id) pairs for biomass reactions

        Raises:
            ValueError: if `submodel` is not a dFBA submodel
            ValueError: if `submodel.dfba_obj` is not a legal python expression, does not
                have the form above, is not a linear function of reaction ids, uses an unknown
                reaction id, or uses an id multiple times
        """
        if submodel.algorithm != SubmodelAlgorithm.dfba:
            raise ValueError("submodel '{}' not a dFBA submodel".format(submodel.name))

        linear_expr = []    # list of (coeff, reaction_id)
        dfba_obj = submodel.dfba_obj
        expression = dfba_obj.expression.expression = dfba_obj.expression.expression.strip()
        expected_nodes = (ast.Add, ast.Expression, ast.Load, ast.Mult, ast.Num, ast.USub,
                          ast.UnaryOp, ast.Name)
        try:
            for node in ast.walk(ast.parse(expression, mode='eval')):
                try:
                    # if linear_expr is empty then an ast.Name is the entire expression
                    if isinstance(node, ast.Name) and not linear_expr:
                        linear_expr.append((1.0, node.id))
                    elif isinstance(node, ast.BinOp):
                        if isinstance(node.op, ast.Mult):
                            self._proc_mult(node, linear_expr)
                        elif isinstance(node.op, ast.Add):
                            self._proc_add(node, linear_expr)
                    elif isinstance(node, expected_nodes):
                        continue
                    else:
                        raise ValueError()
                except ValueError:
                    raise ValueError("Cannot parse objective function '{}' as a linear function of "
                                     "reaction ids.".format(expression))
        except Exception as e:
            raise ValueError("Cannot parse objective function '{}'.".format(expression))

        # error if multiple uses of a reaction in an objective function
        seen = set()
        dupes = []
        for id in [id for coeff, id in linear_expr]:
            if id in seen and id not in dupes:
                dupes.append(id)
            seen.add(id)
        if dupes:
            raise ValueError("Multiple uses of '{}' in objective function '{}'.".format(dupes, expression))
        reactions = []
        biomass_reactions = []

        for coeff, id in linear_expr:

            reaction = submodel.model.get_reactions(id=id)
            if reaction:
                reactions.append((coeff, id),)
                continue

            biomass_reaction = submodel.model.get_biomass_reactions(id=id)
            if biomass_reaction:
                biomass_reactions.append((coeff, id),)
                continue

            raise ValueError("Unknown reaction or biomass reaction id '{}' in objective function '{}'.".format(
                id, expression))
        return (reactions, biomass_reactions)

    @staticmethod
    def _proc_mult(node, linear_expr):
        """ Process a Mult node in the ast.

        Append the Mult node's coefficient and reaction id to `linear_expr`.

        Args:
            node (:obj:`ast.BinOp`): an ast binary operation that uses multiplication
            linear_expr (:obj:`list` of :obj:`tuple`): pairs of (coefficient, reaction_id)

        Raises:
            :obj:`ValueError`: if the Mult node does not have one Name and one Num (which may be negative)
        """
        nums = []
        names = []
        sign = 1.0
        for element in [node.left, node.right]:
            if isinstance(element, ast.Num):
                nums.append(element)
            if isinstance(element, ast.UnaryOp) and isinstance(element.op, ast.USub):
                # the coefficient is negative
                sign = -1.0
                nums.append(element.operand)
            if isinstance(element, ast.Name):
                names.append(element)
        if not (len(nums) == 1 and len(names) == 1):
            raise ValueError("bad Mult")
        linear_expr.append((sign*nums[0].n, names[0].id))

    @staticmethod
    def _proc_add(node, linear_expr):
        """ Process an Add node in the ast.

        Append the Add node's coefficient(s) and reaction id(s) to `linear_expr`.

        Args:
            node (:obj:`ast.BinOp`): an ast binary operation that uses addition
            linear_expr (:obj:`list` of :obj:`tuple`): pairs of (coefficient, reaction_id)

        Raises:
            :obj:`ValueError`: if the Add node does not have a total of 2 Names, Mults, and Adds.
        """
        names = []
        mults = []
        adds = 0
        for element in [node.left, node.right]:
            if isinstance(element, ast.Name):
                names.append(element)
            if isinstance(element, ast.BinOp):
                if isinstance(element.op, ast.Mult):
                    mults.append(element)
                if isinstance(element.op, ast.Add):
                    adds += 1
        if len(names) + len(mults) + adds != 2:
            raise ValueError("bad Add")
        # A Name that's not in a mult. op. is multiplied by 1.0 by default
        # An Add may contain 2 of them
        for name in names:
            linear_expr.append((1.0, name.id))

    @staticmethod
    def assign_linear_objective_fn(submodel, reactions, biomass_reactions):
        """ Assign a linear objective function to a submodel

        Assign a linear objective function parsed by `parse_dfba_submodel_obj_func` to a submodel's
        attributes.

        Args:
            submodel (`Submodel`): a dFBA submodel
            reactions (:obj:`list` of (`float`, `str`)): list of (coeff, id) pairs for reactions
            biomass_reactions (:obj:`list` of (`float`, `str`)): list of (coeff, id) pairs for
                biomass reactions
        """
        of = submodel.dfba_obj
        of.expression.reactions = [get_component_by_id(submodel.model.get_reactions(), id) for coeff, id in reactions]
        of.expression.reaction_coefficients = [coeff for coeff, id in reactions]
        of.expression.biomass_reactions = [get_component_by_id(submodel.model.get_biomass_reactions(), id)
                                           for coeff, id in biomass_reactions]
        of.expression.biomass_reaction_coefficients = [coeff for coeff, id in biomass_reactions]
