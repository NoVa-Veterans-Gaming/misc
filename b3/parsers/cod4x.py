#
# BigBrotherBot(B3) (www.bigbrotherbot.net)
# Copyright (C) 2005 Michael "ThorN" Thornton
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA
#
# CHANGELOG

# 27/01/2016 - 0.1 - 82ndab-Bravo17     - initial release
# 28/01/2016 - 0.2 - ph03n1x            - Correct parser Class name
#                                       - Add unban and tempban methods from ph03n1x
# 06/02/2016 - 0.3 - ph03n1x            - Correct indentation when calling tempban command
#                                       - Limited reason string to 126 chars (max server can handle)
# 10/02/2016 - 0.4 - ph03n1x            - Edited duration to convert float to integer before sending to server
#                                       - removed custom strings in commands
# 06/02/2017 - 0.5x - {FH}Pear          - modified _guidLength from 32 to 19 in support for playerid/steamid
#                                       - added regex for steamid
#                                       - implemented _getpbidFromDump to retrieve 32 char guid from version 1.7
#                                       - patched admin plugin for custom authentication logic for cod4x with playerid
#                                       - appended 'x' to version to distinguish between cod4 and cod4x versions on b3 masterlist
# 06/06/2017 - 0.6x - {FH}Pear          - adjusted parser to detect sv_legacyguidmode and support both "0" and "1" results
# 06/09/2017 - 0.7x - {FH}Pear          - reidentify players when their playerid changes

__author__ = 'ThorN, xlr8or, 82ndab-Bravo17, ph03n1x, {FH}Pear'
__version__ = '0.7x'

import b3.clients
import b3.functions
import b3.parsers.cod4
import b3.parsers.cod2
import re
from threading import Timer


class Cod4XParser(b3.parsers.cod4.Cod4Parser):
    gameName = 'cod4'
    IpsOnly = False
    _guidLength = 19
    _commands = {
        'message': 'tell %(cid)s %(message)s',
        'say': 'say %(message)s',
        'set': 'set %(name)s "%(value)s"',
        'kick': 'clientkick %(cid)s %(reason)s ',
        'ban': 'banclient %(cid)s %(reason)s ',
        'unban': 'unban %(guid)s',
        'tempban': 'tempban %(cid)s %(duration)sm %(reason)s',
        'kickbyfullname': 'kick %(cid)s'
    }

    _regPlayer = re.compile(r'^\s*(?P<slot>[0-9]+)\s+'
                            r'(?P<score>[0-9-]+)\s+'
                            r'(?P<ping>[0-9]+)\s+'
                            r'(?P<guid>[0-9a-f]+)\s+'
                            r'(?P<steamid>[0-9a-f]+)\s+'
                            r'(?P<name>.*?)\s+'
                            r'(?P<last>[0-9]+?)\s*'
                            r'(?P<ip>(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}'
                            r'(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])):?'
                            r'(?P<port>-?[0-9]{1,5})\s*'
                            r'(?P<qport>-?[0-9]{1,5})\s+'
                            r'(?P<rate>[0-9]+)$', re.IGNORECASE | re.VERBOSE)

    _legacyMode = 0

    def __new__(cls, *args, **kwargs):
        patch_b3_clients_cod4x()
        return b3.parsers.cod2.Cod2Parser.__new__(cls)

    def startup(self):
        """
        Called after the parser is created before run().
        """
        #check guid mode
        result = self.write('sv_legacyguidmode')
        
        # change _regPlayer and back to cod4 style
        if result.strip() == '"sv_legacyguidmode" is: "1^7" default: "0^7" info: "outputs pbguid on status command and games_mp.log^7"':
            self._legacyMode = 1
            self._guidLength = 32
            self._regPlayer = b3.parsers.cod4.Cod4Parser._regPlayer
            b3.parsers.cod4.patch_b3_clients()

    def pluginsStarted(self):
        """
        Called after the parser loaded and started all plugins.
        """
        self.patch_b3_admin_plugin()
        self.debug('Admin plugin has been patched')
	
    #override OnJ method in cod.py parser
    #if cod4x player uses a macos machine, their playerid will be their steamid
    def OnJ(self, action, data, match=None):
        codguid = match.group('guid')
        cid = match.group('cid')
        name = match.group('name')
        #normally check length of guid. omit that step
        if len(codguid) < self._guidLength:
            if len(codguid) != 17: #17 is length of steamid
                # invalid guid
                self.verbose2('Invalid GUID: %s. GUID length set to %s' % (codguid, self._guidLength))
                codguid = None

        client = self.getClient(match)

        if client:
            self.verbose2('Client object already exists')
            # lets see if the name/guids match for this client, prevent player mixups after mapchange (not with PunkBuster enabled)
            if not self.PunkBuster:
                if self.IpsOnly:
                    # this needs testing since the name cleanup code may interfere with this next condition
                    if name != client.name:
                        self.debug('This is not the correct client (%s <> %s): disconnecting..' % (name, client.name))
                        client.disconnect()
                        return None
                    else:
                        self.verbose2('client.name in sync: %s == %s' % (name, client.name))
                else:
                    if codguid != client.guid:
                        self.debug('This is not the correct client (%s <> %s): disconnecting...' % (codguid, client.guid))
                        client.disconnect()
                        return None
                    else:
                        self.verbose2('client.guid in sync: %s == %s' % (codguid, client.guid))

            client.state = b3.STATE_ALIVE
            client.name = name
            # join-event for mapcount reasons and so forth
            return self.getEvent('EVT_CLIENT_JOIN', client=client)
        else:
            if self._counter.get(cid) and self._counter.get(cid) != 'Disconnected':
                self.verbose('cid: %s already in authentication queue: aborting join' % cid)
                return None

            self._counter[cid] = 1
            t = Timer(2, self.newPlayer, (cid, codguid, name))
            t.start()
            self.debug('%s connected: waiting for authentication...' % name)
            self.debug('Our authentication queue: %s' % self._counter)
    
    def unban(self, client, reason='', admin=None, silent=False, *kwargs):
        """
        Unban a client.
        :param client: The client to unban
        :param reason: The reason for the unban
        :param admin: The admin who unbanned this client
        :param silent: Whether or not to announce this unban
        """
        if self.PunkBuster:
            if client.pbid:
                result = self.PunkBuster.unBanGUID(client)

                if result:                    
                    admin.message('^3Unbanned^7: %s^7: %s' % (client.exactName, result))

                if admin:
                    variables = self.getMessageVariables(client=client, reason=reason, admin=admin)
                    fullreason = self.getMessage('unbanned_by', variables)
                else:
                    variables = self.getMessageVariables(client=client, reason=reason)
                    fullreason = self.getMessage('unbanned', variables)

                if not silent and fullreason != '':
                    self.say(fullreason)

            elif admin:
                admin.message('%s ^7unbanned but has no punkbuster id' % client.exactName)
        else:
            result = self.write(self.getCommand('unban', guid=client.guid, reason=reason))
            if admin:
                admin.message(result)
                
    def tempban(self, client, reason='', duration=2, admin=None, silent=False, *kwargs):
        """
        Tempban a client.
        :param client: The client to tempban
        :param reason: The reason for this tempban
        :param duration: The duration of the tempban
        :param admin: The admin who performed the tempban
        :param silent: Whether or not to announce this tempban
        """
        duration = b3.functions.time2minutes(duration)
        if isinstance(client, b3.clients.Client) and not client.guid:
            # client has no guid, kick instead
            return self.kick(client, reason, admin, silent)
        elif isinstance(client, str) and re.match('^[0-9]+$', client):
            self.write(self.getCommand('tempban', cid=client, reason=reason))
            return
        elif admin:
            banduration = b3.functions.minutesStr(duration)
            variables = self.getMessageVariables(client=client, reason=reason, admin=admin, banduration=banduration)
            fullreason = self.getMessage('temp_banned_by', variables)
        else:
            banduration = b3.functions.minutesStr(duration)
            variables = self.getMessageVariables(client=client, reason=reason, banduration=banduration)
            fullreason = self.getMessage('temp_banned', variables)

        if self.PunkBuster:
            # punkbuster acts odd if you ban for more than a day
            # tempban for a day here and let b3 re-ban if the player
            # comes back
            duration = str(43200) if int(duration) > 43200 else int(duration)
            self.PunkBuster.kick(client, duration, reason)
        else:
            # The server can only tempban a maximum of 43200 minutes. B3 will handle rebanning if needed.
            duration = 43200 if int(duration) > 43200 else int(duration)
            self.write(self.getCommand('tempban', cid=client.cid, reason=reason[:126], duration=duration))
            
        if not silent and fullreason != '':
            self.say(fullreason)

        self.queueEvent(self.getEvent('EVT_CLIENT_BAN_TEMP', {'reason': reason,
                                                              'duration': duration,
                                                              'admin': admin}, client))
        client.disconnect()

    def _getpbidFromDump(self, cid):
        """
        get pbid from rcon dumpuser
        """
        
        _dump = {}
        
        for _d in self.write('dumpuser %s' % cid).strip().split('\n'): 
            _d = ' '.join(_d.split()).split()
            try:
                _dump[_d[0]] = _d[1]
            except Exception, err:
                pass
        self.debug('from _getpbidFromDump, _dump: %s' % _dump.items())
        try:
            _punkbusterid = _dump['pbguid']
        except KeyError:
            _punkbusterid = ''

        self.debug('from _getpbidFromDump, pbid to be used: %s' % _punkbusterid)
        return _punkbusterid

    def newPlayer(self, cid, codguid, name):
        """
        Build a new client using data in the authentication queue.
        :param cid: The client slot number
        :param codguid: The client GUID
        :param name: The client name
        """
        if not self._counter.get(cid):
            self.verbose('newPlayer thread no longer needed: key no longer available')
            return None
        if self._counter.get(cid) == 'Disconnected':
            self.debug('%s disconnected: removing from authentication queue' % name)
            self._counter.pop(cid)
            return None
        self.debug('newClient: %s, %s, %s' % (cid, codguid, name))
        sp = self.connectClient(cid)
        # PunkBuster is enabled, using PB guid
        if sp and self.PunkBuster:
            self.debug('sp: %s' % sp)
            # test if pbid is valid, otherwise break off and wait for another cycle to authenticate
            if not re.match(self._pbRegExp, sp['pbid']):
                self.debug('PB-id is not valid: giving it another try')
                self._counter[cid] += 1
                t = Timer(4, self.newPlayer, (cid, codguid, name))
                t.start()
                return None
            if self.IpsOnly:
                guid = sp['ip']
                pbid = sp['pbid']
            else:
                guid = sp['pbid']
                pbid = guid # save pbid in both fields to be consistent with other pb enabled databases
            ip = sp['ip']
            if self._counter.get(cid):
                self._counter.pop(cid)
            else:
                return None
        # PunkBuster is not enabled, using codguid
        elif sp:
            if self.IpsOnly:
                codguid = sp['ip']
            if not codguid:
                self.warning('Missing or wrong CodGuid and PunkBuster is disabled: cannot authenticate!')
                if self._counter.get(cid):
                    self._counter.pop(cid)
                return None
            else:
                guid = codguid
                pbid = self._getpbidFromDump(cid)
                ip = sp['ip']
                if self._counter.get(cid):
                    self._counter.pop(cid)
                else:
                    return None
        elif self._counter.get(cid) > 10:
            self.debug('Could not auth %s: giving up...' % name)
            if self._counter.get(cid):
                self._counter.pop(cid)
            return None
        # Player is not in the status response (yet), retry
        else:
            if self._counter.get(cid):
                self.debug('%s not yet fully connected: retrying...#:%s' % (name, self._counter.get(cid)))
                self._counter[cid] += 1
                t = Timer(4, self.newPlayer, (cid, codguid, name))
                t.start()
            else:
                self.warning('All authentication attempts failed')
            return None

        client = self.clients.newClient(cid, name=name, ip=ip, state=b3.STATE_ALIVE,
                                        guid=guid, pbid=pbid, data={'codguid': codguid})

        self.queueEvent(self.getEvent('EVT_CLIENT_JOIN', client=client))

def patch_b3_clients_cod4x():

    def cod4xClientAuthMethod(self):
        self.console.info('Using cod4x authentication')
        if not self.authed and self.guid and not self.authorizing:
            self.authorizing = True
            name = self.name
            ip = self.ip
            pbid = self.pbid
            try:
                inStorage = self.console.storage.getClient(self)
            except KeyError, msg:
                self.console.debug('User guid not found %s: %s', self.guid, msg)
                self.console.debug('Game is cod4x, searching for user guid using pbid: %s', self.pbid)

                match = {'guid': self.pbid}
                clientList = self.console.storage.getClientsMatching(match)

                # if no matches for pbid in the guid field, check the pbid field
                # small bonus, in the future this could eventually be used to aid in tracking playerid changes
                if len(clientList) < 1:
                    pbidMatch = {'pbid': self.pbid}
                    clientList.extend(self.console.storage.getClientsMatching(pbidMatch))

                self.console.debug('clientlist: %s' % clientList)
                for i,item in enumerate(clientList):
                    self.console.verbose2('clientlist[%s]: %s' % (i, item))

                if len(clientList) > 1:
                    self.console.error('More than one client found with pbid: %s', self.pbid)
                    inStorage = False
                elif len(clientList) == 0:
                    self.console.debug('User pbid not found %s', self.pbid)
                    inStorage = False
                else:
                    inStorage = clientList[0]
                    self.console.debug('Client: %s' % inStorage)
                    
                    #set fields in inStorage to self
                    self._set_id(inStorage._get_id())
                    self._set_ip(inStorage._get_ip())
                    self._set_connections(inStorage._get_connections())
                    self._set_guid(inStorage._get_guid())
                    self._set_pbid(inStorage._get_pbid())
                    self._set_name(inStorage._get_name())
                    self._set_auto_login(inStorage._get_auto_login())
                    self._set_maskLevel(inStorage._get_maskLevel())
                    self._set_groupBits(inStorage._get_groupBits())
                    self._set_greeting(inStorage._get_greeting())
                    self._set_timeAdd(inStorage._get_timeAdd())
                    self._set_timeEdit(inStorage._get_timeEdit())
                    self._set_password(inStorage._get_password())
                    self._set_login(inStorage._get_login())
            except Exception, e:
                self.console.error('Auth self.console.storage.getClient(client) - %s' % self, exc_info=e)
                self.authorizing = False
                return False

            #lastVisit = None
            if inStorage:
                self.console.bot('Client found in storage %s: welcome back %s', str(self.id), self.name)
                self.lastVisit = self.timeEdit
                if self.pbid == '':
                    self.pbid = pbid
            else:
                self.console.bot('Client not found in the storage %s: create new', str(self.guid))

            self.connections = int(self.connections) + 1
            self.name = name
            self.ip = ip
            self.save()
            self.authed = True

            self.console.debug('Client authorized: [%s] %s - %s', self.cid, self.name, self.guid)

            # check for bans
            if self.numBans > 0:
                ban = self.lastBan
                if ban:
                    self.reBan(ban)
                    self.authorizing = False
                    return False

            self.refreshLevel()
            self.console.queueEvent(self.console.getEvent('EVT_CLIENT_AUTH', data=self, client=self))
            self.authorizing = False
            return self.authed
        else:
            return False

    b3.clients.Client.auth = cod4xClientAuthMethod

