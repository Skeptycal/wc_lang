""" Tests of SBML utils

:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Date: 2017-09-22
:Copyright: 2017, Karr Lab
:License: MIT
"""

import unittest
import os

# "from libsbml import *" generates "NameError: Unknown C global variable" in pytest,
# presumably from the SWIG wrapper: http://web.mit.edu/svn/src/swig-1.3.25/Lib/python/pyinit.swg
from libsbml import (LIBSBML_OPERATION_SUCCESS, SBMLDocument, OperationReturnValue_toString,
    UnitDefinition, SBMLNamespaces, UNIT_KIND_SECOND, UNIT_KIND_MOLE)

from wc_lang.sbml.util import (wrap_libsbml, LibSBMLError, create_sbml_unit, create_sbml_parameter,
    init_sbml_model)


class TestSbml(unittest.TestCase):

    def setUp(self):
        try:
            self.document = SBMLDocument(3, 2)
        except ValueError:
            raise SystemExit("'SBMLDocument(3, 2)' fails")

    def test_SBML_wrap_libsbml(self):

        self.assertEqual(wrap_libsbml("LIBSBML_OPERATION_SUCCESS"), LIBSBML_OPERATION_SUCCESS)

        with self.assertRaises(LibSBMLError) as context:
            wrap_libsbml("1 +")
        self.assertIn("Syntax error in libsbml method", str(context.exception))

        with self.assertRaises(LibSBMLError) as context:
            wrap_libsbml("x")
        self.assertIn("NameError", str(context.exception))
        self.assertIn("'x' is not defined", str(context.exception))

        id = 'x'
        self.assertEqual(
            wrap_libsbml("self.document.setIdAttribute('{}')".format(id)), LIBSBML_OPERATION_SUCCESS)

        call = "self.document.setIdAttribute('..')"
        with self.assertRaises(LibSBMLError) as context:
            wrap_libsbml(call)
        self.assertIn('LibSBML returned error code', str(context.exception))
        self.assertIn("when executing '{}'".format(call), str(context.exception))

        call = "self.document.appendAnnotation(5)"
        with self.assertRaises(LibSBMLError) as context:
            wrap_libsbml(call)
        self.assertIn("in libsbml method call '{}'".format(call), str(context.exception))

        model = wrap_libsbml("self.document.createModel()")
        self.assertEqual(wrap_libsbml("model.setTimeUnits('second')"), LIBSBML_OPERATION_SUCCESS)

    def test_init_sbml_model(self):
        sbml_model = init_sbml_model(self.document)

        # check the SBML document
        self.assertEqual(self.document.checkConsistency(), 0)
        self.assertEqual(self.document.checkL3v1Compatibility(), 0)

        # check mmol_per_gDW_per_hr
        mmol_per_gDW_per_hr = wrap_libsbml("sbml_model.getUnitDefinition('mmol_per_gDW_per_hr')")
        printed_mmol_per_gDW_per_hr = wrap_libsbml("UnitDefinition.printUnits(mmol_per_gDW_per_hr)")
        '''
        if 'compact' gets fixed, try this
        compact_mmol_per_gDW_per_hr = wrap_libsbml("UnitDefinition.printUnits(mmol_per_gDW_per_hr, compact=True)")
        self.assertIn('(10^-3 mole)^1', compact_mmol_per_gDW_per_hr)
        self.assertIn('(3600 second)^-1', compact_mmol_per_gDW_per_hr)
        self.assertIn('(10^-3 kilogram)^-1', compact_mmol_per_gDW_per_hr)
        '''

    def test_SBML_fbc(self):

        try:
            # use uses the SBML Level 3 Flux Balance Constraints package
            sbmlns = SBMLNamespaces(3, 2, "fbc", 2);
            document = SBMLDocument(sbmlns);
            # mark the fbc package required
            document.setPackageRequired("fbc", True)
        except ValueError:
            raise SystemExit("'SBMLNamespaces(3, 2, 'fbc', 2) fails")

        id = 'x'
        self.assertEqual(
            wrap_libsbml("document.setIdAttribute('{}')".format(id)), LIBSBML_OPERATION_SUCCESS)


class TestLibsbmlInterface(unittest.TestCase):

    def setUp(self):
        sbmlns = SBMLNamespaces(3, 2, "fbc", 2);
        self.sbml_document = SBMLDocument(sbmlns);
        self.sbml_model = wrap_libsbml("self.sbml_document.createModel()")

        self.per_second_id = 'per_second'
        self.per_second = wrap_libsbml("self.sbml_model.createUnitDefinition()")
        wrap_libsbml("self.per_second.setIdAttribute('{}')".format(self.per_second_id))
        create_sbml_unit(self.per_second, UNIT_KIND_SECOND, exponent=-1)

    def test_create_sbml_unit(self):
        per_second = wrap_libsbml("self.sbml_model.createUnitDefinition()")
        exp = -1
        default_scale=0
        default_multiplier=1.0
        unit = create_sbml_unit(per_second, UNIT_KIND_SECOND, exponent=exp)
        self.assertEqual(wrap_libsbml("unit.getExponent()", returns_int=True), exp)
        self.assertEqual(wrap_libsbml("unit.getKind()"), UNIT_KIND_SECOND)
        self.assertEqual(wrap_libsbml("unit.getScale()"), default_scale)
        self.assertEqual(wrap_libsbml("unit.getMultiplier()"), default_multiplier)

        strange_unit = wrap_libsbml("self.sbml_model.createUnitDefinition()")
        exp=-4; scale=3; mult=1.23
        unit = create_sbml_unit(strange_unit, UNIT_KIND_MOLE,
            exponent=exp, scale=scale, multiplier=mult)
        self.assertEqual(wrap_libsbml("unit.getExponent()", returns_int=True), exp)
        self.assertEqual(wrap_libsbml("unit.getKind()"), UNIT_KIND_MOLE)
        self.assertEqual(wrap_libsbml("unit.getScale()"), scale)
        self.assertEqual(wrap_libsbml("unit.getMultiplier()"), mult)

        with self.assertRaises(LibSBMLError) as context:
            unit = create_sbml_unit(strange_unit, -1)
        self.assertIn("LibSBML returned error code", str(context.exception))

    def test_create_sbml_parameter(self):
        id='id1'; name='name1'; value=13; constant=False
        parameter = create_sbml_parameter(self.sbml_model, id, name=name, value=value, constant=constant)
        self.assertEqual(wrap_libsbml("parameter.getIdAttribute()"), id)
        self.assertEqual(wrap_libsbml("parameter.getName()"), name)
        self.assertTrue(wrap_libsbml("parameter.isSetValue()"))
        self.assertFalse(wrap_libsbml("parameter.isSetUnits()"))
        self.assertEqual(wrap_libsbml("parameter.getValue()"), value)
        self.assertEqual(wrap_libsbml("parameter.getConstant()"), constant)

        # test defaults
        id = 'id2'
        parameter = create_sbml_parameter(self.sbml_model, id)
        self.assertEqual(wrap_libsbml("parameter.getIdAttribute()"), id)
        self.assertEqual(wrap_libsbml("parameter.getName()"), '')
        self.assertFalse(wrap_libsbml("parameter.isSetValue()"))
        self.assertEqual(wrap_libsbml("parameter.getConstant()"), True)

        # test units
        id = 'id3'
        parameter = create_sbml_parameter(self.sbml_model, id, units=self.per_second_id)
        self.assertTrue(wrap_libsbml("parameter.isSetUnits()"))
        self.assertEqual(wrap_libsbml("parameter.getUnits()"), self.per_second_id)

        # test Parameter id collision
        with self.assertRaises(ValueError) as context:
            parameter = create_sbml_parameter(self.sbml_model, id)
        self.assertIn("is already in use as a Parameter id", str(context.exception))
