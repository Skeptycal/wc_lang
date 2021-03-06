""" Tests of SBML io

:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Date: 2017-09-22
:Copyright: 2017, Karr Lab
:License: MIT
"""

from math import isnan
from six import iteritems
import mock
import os
import shutil
import tempfile
import unittest
import warnings

import libsbml
from libsbml import Compartment as libsbmlCompartment
from libsbml import Species as libsbmlSpecies
from libsbml import Parameter as libsbmlParameter
from libsbml import Reaction as libsbmlReaction
from libsbml import Model as libsbmlModel
from libsbml import Objective as libsbmlObjective

from obj_model.utils import get_component_by_id
from wc_lang import (SubmodelAlgorithm, Model, DfbaObjective,
                     Species, DfbaObjReaction, Parameter)
from wc_lang.transform.prep_for_wc_sim import PrepareForWcSimTransform
from wc_lang.transform.split_reversible_reactions import SplitReversibleReactionsTransform

from wc_lang.sbml.util import wrap_libsbml, get_SBML_compatibility_method
from wc_lang.io import Reader
import wc_lang.sbml.io as sbml_io


def check_document_against_model(sbml_document, wc_lang_model, test_case):
    """ Compare an SBML document against a wc lang model.

    Check that the `sbml_document` is consistent with the `wc_lang_model`. Many classes and some
    instances in `wc_lang_model` may be missing from `sbml_document`.

    Args:
        sbml_document (:obj:`libsbml.SBMLDocument`): a libsbml SBMLDocument
        wc_lang_model (:obj:`Model`): a wc lang `Model` with species, reactions, compartments or parameters
        test_case (:obj:`unittest.TestCase`): a unittest TestCase
    """
    all_wc_lang_compartments = wc_lang_model.get_compartments()
    all_wc_lang_species = wc_lang_model.get_species()
    all_wc_lang_parameters = wc_lang_model.get_parameters()
    all_wc_lang_reactions = wc_lang_model.get_reactions()
    all_wc_lang_dfba_obj_reactions = wc_lang_model.get_dfba_obj_reactions()
    all_wc_lang_submodels = wc_lang_model.get_submodels()

    for element in sbml_document.getListOfAllElements():

        # compartments
        if isinstance(element, libsbmlCompartment):
            wc_lang_compartment = get_component_by_id(all_wc_lang_compartments,
                                                      element.getIdAttribute())
            test_case.assertEqual(element.getName(), wc_lang_compartment.name)
            test_case.assertEqual(element.getSpatialDimensions(), 3)
            # test_case.assertEqual(element.getSize(), wc_lang_compartment.volume_mean)
            # not checking: comments

        # parameters
        if isinstance(element, libsbmlParameter):
            prefix = 'parameter_'
            if element.getIdAttribute().startswith(prefix):
                # only parameters that start with 'parameter' are wc_lang Parameters
                wc_lang_id = element.getIdAttribute()[len(prefix):]
                wc_lang_parameter = get_component_by_id(all_wc_lang_parameters, wc_lang_id)
                test_case.assertEqual(element.getName(), wc_lang_parameter.name)
                test_case.assertEqual(element.getValue(), wc_lang_parameter.value)
            # not checking: units, SBML parameters not in wc_lang Parameters

        if isinstance(element, libsbmlSpecies):
            wc_lang_id = Species.sbml_id_to_id(element.getIdAttribute())
            wc_lang_species = get_component_by_id(all_wc_lang_species, wc_lang_id)
            test_case.assertEqual(element.getName(), wc_lang_species.species_type.name)
            test_case.assertEqual(element.getCompartment(), wc_lang_species.compartment.id)
            test_case.assertEqual(element.getInitialConcentration(), wc_lang_species.distribution_init_concentration.mean)
            # not checking: comments

        if isinstance(element, libsbmlReaction):
            wc_lang_reaction = get_component_by_id(all_wc_lang_reactions, element.getIdAttribute())
            # test Reaction
            if wc_lang_reaction:
                test_case.assertEqual(element.getName(), wc_lang_reaction.name)
                test_case.assertEqual(element.getReversible(), wc_lang_reaction.reversible)
                test_case.assertEqual(element.getFast(), False)
                # not checking: participants and flux bounds

            wc_lang_dfba_obj_reaction = get_component_by_id(all_wc_lang_dfba_obj_reactions,
                                                            element.getIdAttribute())
            # test DfbaObjReaction
            if wc_lang_dfba_obj_reaction:
                test_case.assertEqual(element.getName(), wc_lang_dfba_obj_reaction.name)
                test_case.assertEqual(element.getReversible(), False)
                test_case.assertEqual(element.getFast(), False)
                # not checking: components, flux bounds, and comments

        if isinstance(element, libsbmlModel):
            # test a submodel
            wc_lang_submodel = get_component_by_id(all_wc_lang_submodels, element.getIdAttribute())
            if wc_lang_submodel.name:
                test_case.assertEqual(element.getName(), wc_lang_submodel.name)
            # not checking: comments

        if isinstance(element, libsbmlObjective):
            # test an DfbaObjective
            test_case.assertEqual(element.getType(), 'maximize')
            test_case.assertEqual(element.getIdAttribute(), DfbaObjective.ACTIVE_OBJECTIVE)
            # not checking: reactions, or dfba_obj_reactions

            # TODO: check remaining elements


class TestSbml(unittest.TestCase):

    MODEL_FILENAME = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'example-model.xlsx')

    def setUp(self):
        self.dirname = tempfile.mkdtemp()
        # read and initialize a model
        self.model = Reader().run(self.MODEL_FILENAME)
        transform = PrepareForWcSimTransform()
        transform.transforms.remove(SplitReversibleReactionsTransform)
        transform.run(self.model)

    def tearDown(self):
        shutil.rmtree(self.dirname)

    def check_sbml_doc(self, sbml_doc):

        # if checkConsistency() returns some errors, print them
        for i in range(wrap_libsbml(sbml_doc.checkConsistency, returns_int=True)):
            print(sbml_doc.getError(i).getShortMessage())
            print(sbml_doc.getError(i).getMessage())
        self.assertEqual(wrap_libsbml(sbml_doc.checkConsistency, returns_int=True), 0)

        # if 0<getNumErrors, print them
        for i in range(wrap_libsbml(sbml_doc.getNumErrors, returns_int=True)):
            print(sbml_doc.getError(i).getShortMessage())
            print(sbml_doc.getError(i).getMessage())
        self.assertEqual(wrap_libsbml(sbml_doc.getNumErrors, returns_int=True), 0)

    def test_SBML_Exchange(self):
        for submodel in self.model.get_submodels():
            if submodel.algorithm == SubmodelAlgorithm.dfba:
                sbml_document = sbml_io.SBMLExchange.write_submodel(submodel)

                self.assertEqual(wrap_libsbml(get_SBML_compatibility_method(sbml_document),
                                              returns_int=True), 0)
                self.check_sbml_doc(sbml_document)
                check_document_against_model(sbml_document, self.model, self)

    def test_SBML_Exchange_warning(self):
        model = Model(id='model')
        met_submodel = model.submodels.create(id='Metabolism', algorithm=SubmodelAlgorithm.ssa)
        model.parameters.append(Parameter(id='param_1'))
        model.parameters.append(Parameter(id='param_1'))

        with self.assertRaisesRegex(UserWarning, 'Some data will not be written because objects are not valid'):
            warnings.simplefilter("ignore")
            warnings.simplefilter("error", UserWarning)
            sbml_document = sbml_io.SBMLExchange.write_submodel(met_submodel)
            warnings.resetwarnings()

    def test_writer(self):
        for algorithms in [None, [SubmodelAlgorithm.dfba]]:
            sbml_documents = sbml_io.Writer.run(self.model, algorithms=algorithms)
            try:
                paths = sbml_io.Writer.run(self.model, algorithms=algorithms, path=self.dirname)
            except Exception as e:
                self.fail("Unexpected sbml_io.Writer.run() exception '{}'".format(e))
            for submodel_id, path in zip(sbml_documents.keys(), paths):

                document = libsbml.SBMLReader().readSBML(path)
                self.check_sbml_doc(document)

                self.assertEqual(document.toSBML(), sbml_documents[submodel_id].toSBML())
                check_document_against_model(document, self.model, self)

    def test_writer_errors(self):
        root_path = os.path.join(os.path.dirname(__file__), 'no_such_dir', 'example-model')
        with self.assertRaises(ValueError) as context:
            sbml_io.Writer.run(self.model, path=root_path)
        self.assertIn('cannot write to directory', str(context.exception))
        self.assertIn('no_such_dir', str(context.exception))

        with self.assertRaisesRegex(ValueError, 'No submodel.algorithm in algorithms'):
            sbml_io.Writer.run(self.model, algorithms=[])

        with mock.patch('libsbml.writeSBMLToFile', return_value=False):
            with self.assertRaisesRegex(ValueError, ' could not be written to '):
                sbml_io.Writer.run(self.model, path=self.dirname)
