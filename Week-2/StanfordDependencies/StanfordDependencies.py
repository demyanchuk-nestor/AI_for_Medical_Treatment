# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function
from abc import ABCMeta, abstractmethod
import os.path

try:
    from urllib import FancyURLopener
except ImportError:
    from urllib.request import FancyURLopener

try:
    string_type = basestring # Python 2.6/7
except NameError:
    string_type = str # Python 3

import warnings

from .CoNLL import Corpus

# ideally, this will be set to the latest version of CoreNLP
DEFAULT_CORENLP_VERSION = '3.5.2'

# where we store downloaded jar files
INSTALL_DIR = '~/.local/share/pystanforddeps'

# list of currently supported representations
# (note that in the online CoreNLP demo, 'collapsed' is called 'enhanced')
REPRESENTATIONS = ('basic', 'collapsed', 'CCprocessed', 'collapsedTree')

class JavaRuntimeVersionError(EnvironmentError):
    """Error for when the Java runtime environment is too old to support
    the specified version of Stanford CoreNLP."""
    def __init__(self):
        message = "Your Java runtime is too old (must be 1.8+ to use " \
                  "CoreNLP version 3.5.0 or later and 1.6+ to use CoreNLP " \
                  "version 1.3.1 or later)"
        super(JavaRuntimeVersionError, self).__init__(message)

class ErrorAwareURLOpener(FancyURLopener):
    def http_error_default(self, url, fp, errcode, errmsg, headers):
        raise ValueError("Error downloading %r: %s %s" %
                         (url, errcode, errmsg))

class StanfordDependencies:
    """Abstract base class for converting Penn Treebank trees to Stanford
    Dependencies. To actually use this, you'll want to instantiate one
    of the backends. The easiest way to do this is via the get_instance()
    helper method.

    If you do not currently have the appropriate Java jar files, the
    download_if_missing flag in the constructor will help you fetch them.
    In this case, you can set version to a string with the CoreNLP version
    you'd like. If unset, it will default to DEFAULT_CORENLP_VERSION.

    Subclasses should (at minimum) override the convert_tree method. They
    may also want to override convert_trees if they require batch
    operation. They may also add their own custom keyword arguments to
    __init__(), convert_tree(), and convert_trees()."""
    __metaclass__ = ABCMeta
    def __init__(self, jar_filename=None, download_if_missing=False,
                 version=None):
        """jar_filename should be the path to a Java jar file with
        classfiles from Stanford CoreNLP or Stanford Parser.

        If download_if_missing is True, it will automatically download
        a jar file and store it locally. By default it will use
        DEFAULT_CORENLP_VERSION but will use the version flag if
        that argument is specified."""
        if not (jar_filename or version is not None or download_if_missing):
            raise ValueError("Must set either jar_filename, version, "
                             "or download_if_missing to True.")

        self.jar_filename = jar_filename
        if not self.jar_filename:
            if version is None:
                version = DEFAULT_CORENLP_VERSION
            filename = 'stanford-corenlp-%s.jar' % version
            self.jar_filename = self.setup_and_get_default_path(filename)
            if download_if_missing:
                self.download_if_missing(version)
    def convert_trees(self, ptb_trees, representation='basic', universal=True,
                      include_punct=True, include_erased=False, **kwargs):
        """Convert a list of Penn Treebank formatted strings (ptb_trees)
        into Stanford Dependencies. The dependencies are represented
        as a list of sentences (CoNLL.Corpus), where each sentence
        (CoNLL.Sentence) is itself a list of CoNLL.Token objects.

        Currently supported representations are 'basic', 'collapsed',
        'CCprocessed', and 'collapsedTree' which behave the same as they
        in the CoreNLP command line tools. (note that in the online
        CoreNLP demo, 'collapsed' is called 'enhanced')

        Additional arguments: universal (if True, use universal
        dependencies if they're available), include_punct (if False,
        punctuation tokens will not be included), and include_erased
        (if False and your representation might erase tokens, those
        tokens will be omitted from the output).

        See documentation on your backend to see if it supports
        further options."""
        kwargs.update(representation=representation, universal=universal,
                      include_punct=include_punct,
                      include_erased=include_erased)
        return Corpus(self.convert_tree(ptb_tree, **kwargs)
                      for ptb_tree in ptb_trees)

    @abstractmethod
    def convert_tree(self, ptb_tree, representation='basic', **kwargs):
        """Converts a single Penn Treebank format tree to Stanford
        Dependencies. With some backends, this can be considerably
        slower than using convert_trees, so consider that if you're
        doing a batch conversion. See convert_trees for more details
        and a listing of possible kwargs."""

    def setup_and_get_default_path(self, jar_base_filename):
        """Determine the user-specific install path for the Stanford
        Dependencies jar if the jar_url is not specified and ensure that
        it is writable (that is, make sure the directory exists). Returns
        the full path for where the jar file should be installed."""
        import os
        import errno
        install_dir = os.path.expanduser(INSTALL_DIR)
        try:
            os.makedirs(install_dir)
        except OSError as ose:
            if ose.errno != errno.EEXIST:
                raise ose
        jar_filename = os.path.join(install_dir, jar_base_filename)
        return jar_filename
    def download_if_missing(self, version=None, verbose=True):
        """Download the jar for version into the jar_filename specified
        in the constructor. Will not overwrite jar_filename if it already
        exists. version defaults to DEFAULT_CORENLP_VERSION (ideally the
        latest but we can't guarantee that since PyStanfordDependencies
        is distributed separately)."""
        if os.path.exists(self.jar_filename):
            return

        jar_url = self.get_jar_url(version)
        if verbose:
            print("Downloading %r -> %r" % (jar_url, self.jar_filename))
        opener = ErrorAwareURLOpener()
        opener.retrieve(jar_url, filename=self.jar_filename)

    @staticmethod
    def _raise_on_bad_representation(representation):
        """Ensure that representation is a known Stanford Dependency
        representation (raises a ValueError if the representation is
        invalid)."""
        if representation not in REPRESENTATIONS:
            repr_desc = ', '.join(map(repr, REPRESENTATIONS))
            raise ValueError("Unknown representation: %r (should be one "
                             "of %s)" % (representation, repr_desc))

    @staticmethod
    def _raise_on_bad_input(ptb_tree):
        """Ensure that ptb_tree is a valid Penn Treebank datatype or
        raises a TypeError. Currently, this requires that ptb_tree is
        a str or basestring (depending on Python version)."""
        if not isinstance(ptb_tree, string_type):
            raise TypeError("ptb_tree is not a string: %r" % ptb_tree)

    @staticmethod
    def _raise_on_bad_jar_filename(jar_filename):
        """Ensure that jar_filename is a valid path to a jar file."""
        if jar_filename is None:
            return

        if not isinstance(jar_filename, string_type):
            raise TypeError("jar_filename is not a string: %r" % jar_filename)

        if not os.path.exists(jar_filename):
            raise ValueError("jar_filename does not exist: %r" % jar_filename)

    @staticmethod
    def get_jar_url(version=None):
        """Get the URL to a Stanford CoreNLP jar file with a specific
        version. These jars come from Maven since the Maven version is
        smaller than the full CoreNLP distributions. Defaults to
        DEFAULT_CORENLP_VERSION."""
        if version is None:
            version = DEFAULT_CORENLP_VERSION

        try:
            string_type = basestring
        except NameError:
            string_type = str

        if not isinstance(version, string_type):
            raise TypeError("Version must be a string or None (got %r)." %
                            version)
        jar_filename = 'stanford-corenlp-%s.jar' % version
        return 'http://search.maven.org/remotecontent?filepath=' + \
               'edu/stanford/nlp/stanford-corenlp/%s/%s' % (version,
                                                            jar_filename)

    @staticmethod
    def get_instance(jar_filename=None, version=None,
                     download_if_missing=True, backend='jpype',
                     **extra_args):
        """This is the typical mechanism of constructing a
        StanfordDependencies instance. The backend parameter determines
        which backend to load (currently can be 'subprocess' or 'jpype').

        To determine which jar file is used, you must specify
        jar_filename, download_if_missing=True, and/or version.
        - If jar_filename is specified, that jar is used and the other two
          flags are ignored.
        - Otherwise, if download_if_missing, we will download a jar file
          from the Maven repository. This jar file will be the latest
          known version of CoreNLP unless the version flag is specified
          (e.g., version='3.4.1') in which case we'll attempt to download
          and use that version. Once downloaded, it will be stored in
          your home directory and not downloaded again.
        - If jar_filename and download_if_missing are not specified,
          version must be set to a version previously downloaded in the
          above step.

        All remaining keyword arguments are passes on to the
        StanfordDependencies backend constructor.

        If the above options are confusing, don't panic! You can leave
        them all blank -- get_instance() is designed to provide the best
        and latest available conversion settings by default."""
        StanfordDependencies._raise_on_bad_jar_filename(jar_filename)
        extra_args.update(jar_filename=jar_filename,
                          download_if_missing=download_if_missing,
                          version=version)
        if backend == 'jpype':
            try:
                from .JPypeBackend import JPypeBackend
                return JPypeBackend(**extra_args)
            except ImportError:
                warnings.warn('Error importing JPypeBackend, '
                              'falling back to SubprocessBackend.')
                backend = 'subprocess'
            except RuntimeError as r:
                warnings.warn('RuntimeError with JPypeBackend (%s), '
                              'falling back to SubprocessBackend.' % r[0])
                backend = 'subprocess'
            except TypeError as t:
                warnings.warn('TypeError with JPypeBackend (%s), '
                              'falling back to SubprocessBackend.' % t[0])
                backend = 'subprocess'

        if backend == 'subprocess':
            from .SubprocessBackend import SubprocessBackend
            return SubprocessBackend(**extra_args)

        raise ValueError("Unknown backend: %r (known backends: "
                         "'subprocess' and 'jpype')" % backend)

# convenience alias so we don't need to say
#   sd = StanfordDependencies.StanfordDependencies.get_instance()
get_instance = StanfordDependencies.get_instance
