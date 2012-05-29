import os
import sublime
import sublime_plugin
import threading
import subprocess
import functools
import tempfile
import os.path
import re

class FoldersListCommand(sublime_plugin.WindowCommand, object):
  def run(self, edit=None):
    s = sublime.load_settings("Folders.sublime-settings")
    command = ['ls', s.get('base_folder')]
    self.run_command(command, self.list_folders, working_dir=os.getenv("HOME"))

  def active_view(self):
    return self.window.active_view()

  def _active_file_name(self):
    view = self.active_view()
    if view and view.file_name() and len(view.file_name()) > 0:
      return view.file_name()

  def get_working_dir(self):
    file_name = self._active_file_name()
    if file_name:
      return os.path.dirname(file_name)
    else:
      return self.window.folders()[0]

  def run_command(self, command, callback=None, show_status=True, filter_empty_args=True, no_save=False, **kwargs):
    if filter_empty_args:
      command = [arg for arg in command if arg]
    if 'working_dir' not in kwargs:
      kwargs['working_dir'] = self.get_working_dir()
    if 'fallback_encoding' not in kwargs and self.active_view() and self.active_view().settings().get('fallback_encoding'):
      kwargs['fallback_encoding'] = self.active_view().settings().get('fallback_encoding').rpartition('(')[2].rpartition(')')[0]

    s = sublime.load_settings("Git.sublime-settings")
    if s.get('save_first') and self.active_view() and self.active_view().is_dirty() and not no_save:
      self.active_view().run_command('save')
    if command[0] == 'git' and s.get('git_command'):
      command[0] = s.get('git_command')

    thread = CommandThread(command, callback, **kwargs)
    thread.start()

    if show_status:
      message = kwargs.get('status_message', False) or ' '.join(command)
      sublime.status_message(message)

  def list_folders(self, result):
    self.results = [r.split('\a', 2) for r in result.strip().split('\n')]
    self.window.show_quick_panel(self.results, self.log_panel_done)

  def log_panel_done(self, picked):
    if 0 > picked < len(self.results):
      return
    item = self.results[picked]
    # the commit hash is the first thing on the second line
    self.open_folder(item[0])

  def open_folder(self, result):
    # self.scratch(result, title="Testing")
    s = sublime.load_settings("Folders.sublime-settings")
    command = ['/Applications/Sublime Text 2.app/Contents/SharedSupport/bin/subl', os.getenv("HOME")+'/'+s.get('base_folder')+'/'+result]
    self.run_command(command)


class CommandThread(threading.Thread):
  def __init__(self, command, on_done, working_dir="", fallback_encoding="", **kwargs):
    threading.Thread.__init__(self)
    self.command = command
    self.on_done = on_done
    self.working_dir = working_dir
    if "stdin" in kwargs:
      self.stdin = kwargs["stdin"]
    else:
      self.stdin = None
      if "stdout" in kwargs:
        self.stdout = kwargs["stdout"]
      else:
        self.stdout = subprocess.PIPE
        self.fallback_encoding = fallback_encoding
        self.kwargs = kwargs

  def run(self):
    try:
      # Per http://bugs.python.org/issue8557 shell=True is required to
      # get $PATH on Windows. Yay portable code.
      shell = os.name == 'nt'
      if self.working_dir != "":
        os.chdir(self.working_dir)

        proc = subprocess.Popen(self.command,
          stdout=self.stdout, stderr=subprocess.STDOUT,
          stdin=subprocess.PIPE,
          shell=shell, universal_newlines=True)
        output = proc.communicate(self.stdin)[0]
        if not output:
          output = ''
      # if sublime's python gets bumped to 2.7 we can just do:
      # output = subprocess.check_output(self.command)
      main_thread(self.on_done,
        _make_text_safeish(output, self.fallback_encoding), **self.kwargs)
    except subprocess.CalledProcessError, e:
      main_thread(self.on_done, e.returncode)
    except OSError, e:
      if e.errno == 2:
        main_thread(sublime.error_message, "Git binary could not be found in PATH\n\nConsider using the git_command setting for the Git plugin\n\nPATH is: %s" % os.environ['PATH'])
      else:
        raise e


def main_thread(callback, *args, **kwargs):
  # sublime.set_timeout gets used to send things onto the main thread
  # most sublime.[something] calls need to be on the main thread
  sublime.set_timeout(functools.partial(callback, *args, **kwargs), 0)

def _make_text_safeish(text, fallback_encoding):
  # The unicode decode here is because sublime converts to unicode inside
  # insert in such a way that unknown characters will cause errors, which is
  # distinctly non-ideal... and there's no way to tell what's coming out of
  # git in output. So...
  try:
    unitext = text.decode('utf-8')
  except UnicodeDecodeError:
    unitext = text.decode(fallback_encoding)
  return unitext
