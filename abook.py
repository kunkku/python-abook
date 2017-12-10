# Python library to convert between Abook and vCard
#
# Copyright (C) 2013-2017  Jochen Sprickerhof
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Python library to convert between Abook and vCard"""

from hashlib import sha1
from os.path import getmtime, dirname, expanduser, join
from socket import getfqdn
from threading import Lock
from configparser import ConfigParser
from vobject import readOne, readComponents, vCard
from vobject.vcard import Name, Address


class Abook(object):
    """Represents a Abook addressbook"""

    def __init__(self, filename=None):
        """Constructor

        filename -- the filename to load
        """
        self.filename = filename
        self._last_modified = 0
        self._events = []
        self._lock = Lock()

    def to_vcf(self):
        """ Converts to vCard string"""
        with self._lock:
            if getmtime(self.filename) > self._last_modified:
                self._events = self.to_vcards()
                self._last_modified = getmtime(self.filename)

        return '\r\n'.join([v.serialize() for v in self._events])

    def append(self, text):
        """Appends an address to the Abook addressbook"""
        return self.append_vobject(readOne(text))

    def append_vobject(self, text):
        """Appends an address to the Abook addressbook"""
        book = ConfigParser(default_section='format')
        with self._lock:
            book.read(self.filename)
            section = max([int(k) for k in book.keys()[1:]])
            Abook.to_abook(text, str(section + 1), book, self.filename)
            with open(self.filename, 'w') as fp:
                book.write(fp, False)

        return Abook._gen_uid(section, text.fn.value)

    def remove(self, name):
        """Removes an address to the Abook addressbook"""
        uid = name.split('@')[0].split('-')
        if len(uid) != 2:
            return

        book = ConfigParser(default_section='format')
        with self._lock:
            book.read(self.filename)
            linehash = sha1(book[uid[0]]['name'].encode('utf-8')).hexdigest()
            if linehash == uid[1]:
                del book[uid[0]]
                with open(self.filename, 'w') as fp:
                    book.write(fp, False)

    def replace(self, name, text):
        """Updates an address to the Abook addressbook"""
        return self.replace_vobject(name, readOne(text))

    def replace_vobject(self, name, text):
        """Updates an address to the Abook addressbook"""
        uid = name.split('@')[0].split('-')
        if len(uid) != 2:
            return

        book = ConfigParser(default_section='format')
        with self._lock:
            book.read(self.filename)
            linehash = sha1(book[uid[0]]['name'].encode('utf-8')).hexdigest()
            if linehash == uid[1]:
                Abook.to_abook(text, uid[0], book, self.filename)
                with open(self.filename, 'w') as fp:
                    book.write(fp, False)

        return Abook._gen_uid(uid[0], text.fn.value)

    @staticmethod
    def _gen_uid(index, name):
        """Generates a UID based on the index in the Abook file and the hash of the name"""
        return '%s-%s@%s' % (index, sha1(name.encode('utf-8')).hexdigest(), getfqdn())

    @staticmethod
    def _gen_name(name):
        """Splits the name into family and given name"""
        return Name(family=name.split(' ')[-1], given=name.split(' ')[:-1])

    @staticmethod
    def _gen_addr(entry):
        """Generates a vobject Address objects"""
        return Address(street=entry.get('address', ''),
                       extended=entry.get('address2', ''),
                       city=entry.get('city', ''),
                       region=entry.get('state', ''),
                       code=entry.get('zip', ''),
                       country=entry.get('country', ''))

    def _add_photo(self, card, name):
        """Tries to load a photo and add it to the vCard"""
        try:
            photo_file = join(dirname(self.filename), 'photo/%s.jpeg' % name)
            jpeg = open(photo_file, 'rb').read()
            photo = card.add('photo')
            photo.type_param = 'jpeg'
            photo.encoding_param = 'b'
            photo.value = jpeg
        except IOError:
            pass

    def _to_vcard(self, entry):
        """Returns a vobject vCard of the Abook entry"""
        card = vCard()

        card.add('uid').value = Abook._gen_uid(entry.name, entry['name'])
        card.add('fn').value = entry['name']
        card.add('n').value = Abook._gen_name(entry['name'])

        if 'email' in entry:
            for email in entry['email'].split(','):
                card.add('email').value = email

        addr_comps = ['address', 'address2', 'city', 'country', 'zip', 'country']
        if any(comp in entry for comp in addr_comps):
            card.add('adr').value = Abook._gen_addr(entry)

        if 'other' in entry:
            tel = card.add('tel')
            tel.value = entry['other']

        if 'phone' in entry:
            tel = card.add('tel')
            tel.type_param = 'home'
            tel.value = entry['phone']

        if 'workphone' in entry:
            tel = card.add('tel')
            tel.type_param = 'work'
            tel.value = entry['workphone']

        if 'mobile' in entry:
            tel = card.add('tel')
            tel.type_param = 'cell'
            tel.value = entry['mobile']

        if 'nick' in entry:
            card.add('nickname').value = entry['nick']

        if 'url' in entry:
            card.add('url').value = entry['url']

        if 'notes' in entry:
            card.add('note').value = entry['notes']

        self._add_photo(card, entry['name'])

        return card

    def get_uids(self, filename=None):
        """Return a list of UIDs
        filename  -- unused, for API compatibility only
        """
        book = ConfigParser(default_section='format')
        book.read(self.filename)

        return [Abook._gen_uid(entry, book[entry]['name']) for entry in book.sections()]

    def to_vcards(self):
        """Returns a list of vobject vCards"""
        book = ConfigParser(default_section='format')
        book.read(self.filename)

        return [self._to_vcard(book[entry]) for entry in book.sections()]

    def to_vobject(self, filename=None, uid=None):
        """Returns the vobject corresponding to the uid
        filename  -- unused, for API compatibility only
        uid -- the UID to get (required)
        """
        book = ConfigParser(default_section='format')
        book.read(self.filename)

        uid = uid.split('@')[0].split('-')
        if len(uid) != 2:
            return
        linehash = sha1(book[uid[0]]['name'].encode('utf-8')).hexdigest()

        if linehash == uid[1]:
            return self._to_vcard(book[uid[0]])

    @staticmethod
    def _conv_adr(adr, entry):
        """Converts to Abook address format"""
        if adr.value.street:
            entry['address'] = adr.value.street
        if adr.value.extended:
            entry['address2'] = adr.value.extended
        if adr.value.city:
            entry['city'] = adr.value.city
        if adr.value.region:
            entry['state'] = adr.value.region
        if adr.value.code and adr.value.code != '0':
            entry['zip'] = adr.value.code
        if adr.value.country:
            entry['country'] = adr.value.country

    @staticmethod
    def _conv_tel_list(tel_list, entry):
        """Converts to Abook phone types"""
        for tel in tel_list:
            if not hasattr(tel, 'TYPE_param'):
                entry['other'] = tel.value
            elif tel.TYPE_param.lower() == 'home':
                entry['phone'] = tel.value
            elif tel.TYPE_param.lower() == 'work':
                entry['workphone'] = tel.value
            elif tel.TYPE_param.lower() == 'cell':
                entry['mobile'] = tel.value

    @staticmethod
    def to_abook(card, section, book, bookfile=None):
        """Converts a vCard to Abook"""
        book[section] = {}
        book[section]['name'] = card.fn.value

        if hasattr(card, 'email'):
            book[section]['email'] = ','.join([e.value for e in card.email_list])

        if hasattr(card, 'adr'):
            Abook._conv_adr(card.adr, book[section])

        if hasattr(card, 'tel_list'):
            Abook._conv_tel_list(card.tel_list, book[section])

        if hasattr(card, 'nickname'):
            book[section]['nick'] = card.nickname.value

        if hasattr(card, 'url'):
            book[section]['url'] = card.url.value

        if hasattr(card, 'note'):
            book[section]['notes'] = card.note.value

        if hasattr(card, 'photo') and bookfile:
            try:
                photo_file = join(dirname(bookfile), 'photo/%s.%s' % (card.fn.value, card.photo.TYPE_param))
                open(photo_file, 'wb').write(card.photo.value)
            except IOError:
                pass

    @staticmethod
    def abook_file(vcard, bookfile):
        """Write a new Abook file with the given vcards"""
        book = ConfigParser(default_section='format')

        book['format'] = {}
        book['format']['program'] = 'abook'
        book['format']['version'] = '0.6.1'

        for (i, card) in enumerate(readComponents(vcard.read())):
            Abook.to_abook(card, str(i), book, bookfile)
        with open(bookfile, 'w') as fp:
            book.write(fp, False)


def abook2vcf():
    """Command line tool to convert from Abook to vCard"""
    from argparse import ArgumentParser, FileType
    from os.path import expanduser
    from sys import stdout

    parser = ArgumentParser(description='Converter from Abook to vCard syntax.')
    parser.add_argument('infile', nargs='?', default=join(expanduser('~'), '.abook/addressbook'),
                        help='The Abook file to process (default: ~/.abook/addressbook)')
    parser.add_argument('outfile', nargs='?', type=FileType('w'), default=stdout,
                        help='Output vCard file (default: stdout)')
    args = parser.parse_args()

    args.outfile.write(Abook(args.infile).to_vcf())


def vcf2abook():
    """Command line tool to convert from vCard to Abook"""
    from argparse import ArgumentParser, FileType
    from sys import stdin

    parser = ArgumentParser(description='Converter from vCard to Abook syntax.')
    parser.add_argument('infile', nargs='?', type=FileType('r'), default=stdin,
                        help='Input vCard file (default: stdin)')
    parser.add_argument('outfile', nargs='?', default=join(expanduser('~'), '.abook/addressbook'),
                        help='Output Abook file (default: ~/.abook/addressbook)')
    args = parser.parse_args()

    Abook.abook_file(args.infile, args.outfile)
