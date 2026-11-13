def discovery_args(directory, pattern='test*.py'):
    return ['python', '-m', 'unittest', 'discover', '-s', directory]
