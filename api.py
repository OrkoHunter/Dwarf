from django.core.management import call_command
from redis_cache import RedisCache

import dwarf.extensions
from . import version

import subprocess, shutil, os, stat


redis = RedisCache('127.0.0.1:6379', {'PASSWORD': 'S3kr1t!', 'DB': 2})


class ExtensionAlreadyInstalled(Exception):
    pass

class ExtensionNotInIndex(Exception):
    pass

class ExtensionNotFound(Exception):
    pass


class CacheAPI:
    """Represents a connection to the cache backend.
    This class is used to store keys into and retrieve keys
    from the cache.

    Parameters
    ----------
    extension : Optional[str]

    Attributes
    -----------
    backend
        The cache backend the :class:`Cache` connects to.
    extension : Optional[str]
        If specified, the :class:`Cache` stores data in that
        extension's own storage area.
    """

    def __init__(self, extension=""):
        self.backend = redis
        self.extension = extension

    def get(self, key, default=None):
        """Retrieves a key's value from the cache.
        
        Parameters
        ----------
        key : str
            The key to retrieve from the cache.
        default : Optional
            The value to return if the key wasn't found in the database.
        """
        
        if not self.extension:
            return self.backend.get(key='_'.join(['dwarf', key]), default=default)
        return self.backend.get(key='_'.join(['dwarf', self.extension, key]), default=default)

    def set(self, key, value, timeout=None):
        """Sets a key in the cache.
        
        Parameters
        ----------
        key : str
            The key to set in the cache.
        """
        
        if not self.extension:
            return self.backend.set(key='_'.join(['dwarf', key]), value=value, timeout=timeout)
        return self.backend.set(key='_'.join(['dwarf', self.extension, key]), value=value, timeout=timeout)

    def get_many(self, keys):
        """Retrieves an iterable of keys' values from the cache.
        Returns a list of the keys' values.
        If a key wasn't found, it inserts None into the list of values instead.
        
        Parameters
        ----------
        keys : iter of str
            The keys to retrieve from the cache.
        """
        
        actual_keys = []
        if not self.extension:
            for key in keys:
                actual_keys.append('_'.join(['dwarf', key]))
        else:
            for key in keys:
                actual_keys.append('_'.join(['dwarf', self.extension, key]))
        return list(self.backend.get_many(keys=actual_keys).values())

    def set_many(self, keys, values, timeout=None):
        """Sets an iterable of keys in the cache.
        If a key wasn't found, it inserts None into the list of values instead.
        
        Parameters
        ----------
        keys : iter of str
            The keys to retrieve from the cache.
        values : iter
            An iterable of values to assign to the keys.
        timeout : Optional[int]
            After this amount of time (in seconds), the key will be deleted.
        """
        
        actual_keys = []
        if not self.extension:
            for key in keys:
                actual_keys.append('_'.join(['dwarf', key]))
        else:
            for key in keys:
                actual_keys.append('_'.join(['dwarf', self.extension, key]))
        return list(self.backend.set_many(data=dict(zip(actual_keys, values)), timeout=timeout).values())

    def delete(self, key):
        """Deletes a key from the cache.
        
        Parameters
        ----------
        key : str
            The key to delete from the cache.
        """
        
        if not self.extension:
            return self.backend.delete(key='_'.join(['dwarf', key]))
        return self.backend.delete(key='_'.join(['dwarf', self.extension, key]))


class BaseAPI:
    """Internal API that manages extensions and makes data available that
    needs to be loaded before Django loads any models.
    It also makes rebooting available to the bot and the web interface.
    
    Attributes
    ----------
    cache : :class:`CacheAPI`
        The cache backend connection of the API.
    """

    def __init__(self):
        self.cache = CacheAPI()

    def get_token(self):
        """Retrieves the bot's token."""
        return self.cache.get('token')

    def set_token(self, token):
        """Sets the bot's token.
        
        Parameters
        ----------
        token : str
            The bot's new token.
        """
        
        self.cache.set('token', token)

    def delete_token(self):
        self.cache.delete('token')

    def install_extension(self, extension):
        """Installs an extension via the Dwarf Extension Index.
        
        Parameters
        ----------
        extension : str
            The name of the extension that should be installed.
        """
        
        extensions = self.get_extensions()
        if extension in extensions:
            raise ExtensionAlreadyInstalled(extension)
        
        try:
            subprocess.run(['git', 'clone', dwarf.extensions.index[extension]['repository'], 'dwarf/' + extension])
        except KeyError:
            raise ExtensionNotInIndex(extension)
        
        extensions.append(extension)
        self._set_extensions(extensions)

    def uninstall_extension(self, extension):
        """Uninstalls an installed extension.
        Throws :exception:`ExtensionNotFound`
        if the extension is not installed.
        
        Parameters
        ----------
        extension : str
            The name of the extension that should be installed.
        """
        
        def onerror(func, path, exc_info):
            """`shutil.rmtree` error handler that helps deleting read-only files on Windows."""
            if not os.access(path, os.W_OK):
                os.chmod(path, stat.S_IWUSR)
                func(path)
            else:
                raise
        
        extensions = self.get_extensions()
        if extension not in extensions:
            raise ExtensionNotFound(extension)
        
        shutil.rmtree('dwarf/' + extension, onerror=onerror)
        
        extensions.remove(extension)
        self.set_extensions(extensions)

    def get_extensions(self):
        """Retrieves the names of all installed extensions and
        returns them as a list of `str`s.
        """
        
        return self.cache.get('extensions', default=[])

    def set_extensions(self, extensions):
        """Sets the list of the installed extensions.
        
        Parameters
        ----------
        extensions : iter of str
            The names of the extensions to set as installed.
        """
        
        self.cache.set('extensions', extensions)
   
    @staticmethod
    def get_dwarf_version():
        """Returns Dwarf's version."""
        
        return version
