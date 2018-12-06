import pkg_resources

with open(pkg_resources.resource_filename('wc_lang', 'VERSION'), 'r') as file:
    __version__ = file.read().strip()
# :obj:`str`: version

# API
from .core import (TimeUnit, TaxonRank, CompartmentType, VolumeUnit, DensityUnit,
                   SubmodelAlgorithm, SpeciesTypeType, MoleculeCountUnit,
                   RandomDistribution, ConcentrationUnit,
                   ReactionParticipantUnit, RateLawDirection, RateLawType, ReactionRateUnit, ReactionFluxUnit,
                   DfbaObjectiveUnit, DfbaCellSizeUnit, DfbaObjectiveCoefficientUnit, DfbaNetComponentUnit,
                   ParameterType, EvidenceType, ReferenceType,
                   Model, Taxon, Submodel, Compartment,
                   SpeciesType, Species, DistributionInitConcentration, DfbaObjective, DfbaObjectiveExpression,
                   Observable, ObservableExpression,
                   Function, FunctionExpression,
                   Reaction, SpeciesCoefficient, RateLaw, RateLawExpression,
                   DfbaNetComponent, DfbaNetReaction, Parameter,
                   StopCondition, StopConditionExpression, StopConditionUnit,
                   DatabaseReference, Reference)
from . import config
from . import expression
from . import io
from . import sbml
from . import transform
from . import util
