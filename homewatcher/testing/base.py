#!/usr/bin/python3

# Copyright (C) 2014-2017 Cyrille Defranoux
#
# This file is part of Homewatcher.
#
# Homewatcher is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Homewatcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Homewatcher. If not, see <http://www.gnu.org/licenses/>.
#
# For any question, feature requests or bug reports, feel free to contact me at:
# knx at aminate dot net

import sys
import os
import subprocess
import unittest
import time
import traceback
import inspect
import stat
import pwd, grp
import shutil

from pyknx import logger, linknx
from pyknx.testing import base
from pyknx.communicator import Communicator
from homewatcher import configuration, configurator
import logging
import test
from homewatcher.sensor import *
from homewatcher.alarm import *

class TestCaseBase(base.WithLinknxTestCase):
    class ExecuteActionMock(object):
        def __init__(self, linknx, test):
            self.realExecute = linknx.executeAction
            self.test = test

        def executeAction(self, actionXml):
            logger.reportDebug('executeActionMock: {0}'.format(actionXml.toxml()))
            actionNode = actionXml.getElementsByTagName('action')[0]
            if actionNode.getAttribute('type') == 'shell-cmd':
                self.test.assertIsNone(self.test.shellCmdInfo, 'An unconsumed shell command is about to be deleted. It is likely to be an unexpected shell command. Details are {0}'.format(self.test.shellCmdInfo))
                self.test.shellCmdInfo = {'action' : actionXml, 'date' : time.ctime()}
                logger.reportInfo('executeAction mock received {0}'.format(self.test.shellCmdInfo))
            self.realExecute(actionXml)

    def sendEmailMock(self, actionXml):
        logger.reportDebug('sendEmailMock: {0}'.format(actionXml.toxml()))
        self.assertIsNone(self.emailInfo, 'An unconsumed email is about to be deleted. It is likely to be an unexpected email. Details are {0}'.format(self.emailInfo))
        self.emailInfo = {'action' : actionXml, 'date' : time.ctime()}
        logger.reportInfo('sendEmail mock received {0}'.format(self.emailInfo))

    def assertEmail(self, purpose, to, subject, attachments, body=None, consumesEmail=True):
        self.assertIsNotNone(self.emailInfo, 'No email has been sent for {0}.'.format(purpose))

        if isinstance(to, list):
            if len(to) > 1:
                self.fail('Multiple recipients are not allowed.')
            else:
                recipient = to[0]
        else:
            recipient = to

        actionXml = self.emailInfo['action']
        actionNode = actionXml.getElementsByTagName('action')[0]
        self.assertEqual(actionNode.getAttribute('to'), recipient)
        self.assertEqual(actionNode.getAttribute('subject'), subject)
        if body != None:
            # Check first child only, so that we do not take the footer which is
            # not significant enough to deserve testing.
            self.assertEqual(actionNode.childNodes[0].data, body)

        if consumesEmail: self.emailInfo = None

    def assertShellCmd(self, cmd, consumes=True):
        self.assertIsNotNone(self.shellCmdInfo, 'No shell command has been sent.')

        actionXml = self.shellCmdInfo['action']
        actionNode = actionXml.getElementsByTagName('action')[0]
        self.assertEqual(actionNode.getAttribute('cmd'), cmd)

        if consumes: self.shellCmdInfo = None

    def setUp(self, linknxConfFile='linknx_test_conf.xml', usesCommunicator=True,  hwConfigFile=os.path.join(os.path.dirname(__file__), 'homewatcher_test_conf.xml')):
        usesLinknx = linknxConfFile != None
        communicatorAddress = ('localhost', 1031) if usesCommunicator else None
        userScript = os.path.join(os.path.dirname(configuration.__file__), 'linknxuserfile.py')
        userScriptArgs = {'hwconfig':hwConfigFile}
        try:
            if usesCommunicator:
                linknxPatchedFile = tempfile.mkstemp(suffix='.xml', text=True)[1]
                hwConfigurator = configurator.Configurator(hwConfigFile, linknxConfFile, linknxPatchedFile)
                hwConfigurator.generateConfig()
                hwConfigurator.writeConfig()
            else:
                linknxPatchedFile = None
            base.WithLinknxTestCase.setUp(self, linknxConfFile=linknxPatchedFile, communicatorAddr=communicatorAddress, patchLinknxConfig=False, userScript=userScript, userScriptArgs=userScriptArgs)
        finally:
            if linknxPatchedFile is not None: os.remove(linknxPatchedFile)
        self.homewatcherScriptsDirectory = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.homewatcherModulesDirectory = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
        try:
            # Redirect the emailing capability of the daemon.
            if self.alarmDaemon:
                logger.reportInfo('Redirecting email capability of the alarm daemon to the mock for testing.')
                self.alarmDaemon.sendEmail = self.sendEmailMock
                mock = TestCaseBase.ExecuteActionMock(self.alarmDaemon.linknx, self)
                self.alarmDaemon.linknx.executeAction = mock.executeAction
            else:
                logger.reportInfo('No alarm daemon. Email redirection is not set.')
            self.emailInfo = None
            self.shellCmdInfo = None
        except:
            logger.reportException('Error in setUp.')
            self.tearDown()
            self.fail('Test setup failed.')
            raise

    @property
    def alarmDaemon(self):
        userModule = self.communicator._userModule if self.communicator else None
        if userModule is None: return None

        return userModule.alarmDaemon

    @property
    def alarmModeObject(self):
        return self.alarmDaemon.modeValueObject

    # @property
    # def alarmDaemon(self):
        # userModule = self.communicator._userModule
        # if userModule is None: return None
# 
        # return userModule.alarmDaemon

    def tearDown(self):
        logger.reportInfo('Tearing down...')

        base.WithLinknxTestCase.tearDown(self)

    def changeAlarmMode(self, newMode, emailAddressesForNotification):
        self.alarmDaemon.currentMode = newMode

        # Check that mode is now changed.
        self.waitDuring(1.5, 'Waiting for linknx to handle mode change')
        self.assertEqual(self.alarmDaemon.currentMode, self.alarmDaemon.getMode(newMode), 'Alarm mode in daemon should now be synchronized.')

        # Check email notification.
        expectedSubjectStart = 'Entered mode {0}'.format(newMode)
        self.waitDuring(1, 'Waiting for email notification')
        if emailAddressesForNotification != None: self.assertEmail('mode change', emailAddressesForNotification, expectedSubjectStart, [], body=None)

        # Check shell command.
        self.assertShellCmd('echo "Entered mode {0}"'.format(newMode))

    def assertAlert(self, sensorsInPrealert, sensorsInAlert, sensorsInPersistentAlert):
        # Sort sensors by alert types.
        sortedPrealertSensors = self._sortSensors(sensorsInPrealert)
        sortedAlertSensors = self._sortSensors(sensorsInAlert)
        sortedPostalertSensors = self._sortSensors(sensorsInPersistentAlert)

        # Check each alert type.
        for alert in self.alarmDaemon.alerts:
            self._assertStateOfSingleAlertType(alert, sortedPrealertSensors[alert], sortedAlertSensors[alert], sortedPostalertSensors[alert])

    def _sortSensors(self, inputSensors):
        sortedSensors = {}
        for alert in self.alarmDaemon.alerts:
            sortedSensors[alert] = []

        for s in inputSensors:
            sortedSensors[s.alert].append(s)

        return sortedSensors

    def _assertStateOfSingleAlertType(self, alert, sensorsInPrealert, sensorsInAlert, sensorsInPersistentAlert):
        # Define constants.
        persistentAlertObject = alert.persistenceObject

        # Check integrity of parameters.
        self.assertTrue(not sensorsInPrealert or not sensorsInAlert, 'There should not be some sensors in prealert if some are in alert.')
        self.assertEqual(len(set(sensorsInAlert).intersection(set(sensorsInPersistentAlert))), len(sensorsInAlert), 'Some sensors in alert are not in persistent alert.')

        # Check persistent alert.
        expectedPersistentValue = len(sensorsInPersistentAlert) > 0
        if persistentAlertObject != None:
            self.assertEqual(persistentAlertObject.value, expectedPersistentValue, 'Persistence for "{1}" should be {2}={0}'.format(expectedPersistentValue, alert, persistentAlertObject))
        if sensorsInPrealert:
            expectedStatus = Alert.Status.INITIALIZING
        elif sensorsInAlert:
            expectedStatus = Alert.Status.ACTIVE
        elif sensorsInPersistentAlert:
            expectedStatus = Alert.Status.PAUSED
        else:
            expectedStatus = Alert.Status.STOPPED
        self.assertEqual(alert.status, expectedStatus)
        for s in self.alarmDaemon.sensors:
            if s.alert != alert: continue
            self.assertEqual(s.isAlertActive, s in sensorsInAlert, '{0} alert should be {1}'.format(s, s in sensorsInAlert))
            self.assertEqual(s.persistenceObject != None and s.persistenceObject.value, s in sensorsInPersistentAlert, '{0} persistent alert should be {1}'.format(s, s in sensorsInPersistentAlert))
            self.assertEqual(s.isInPrealert, s in sensorsInPrealert, '{0}\'s prealert should be {1}'.format(s, s in sensorsInPrealert))
