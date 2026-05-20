# Fish completion for svg2fcm.
#
# Install: copy this file into ~/.config/fish/completions/, then open
# a new shell.
#     cp svg2fcm.fish ~/.config/fish/completions/

# Flags.
complete -c svg2fcm -s h -l help        -d 'Show help message and exit'
complete -c svg2fcm -s o -l output      -r -F -d 'Output .fcm file, directory, or fixed-SVG path'
complete -c svg2fcm -s v -l verbose     -d 'Increase verbosity (repeat for debug)'
complete -c svg2fcm -s n -l no-group    -d 'Emit one piece per shape (legacy)'
complete -c svg2fcm      -l fix-viewbox -d 'Rewrite the SVG with a synthesised viewBox and exit'
complete -c svg2fcm      -l no-viewbox-fix -d 'Skip the implicit viewBox fix before conversion'
complete -c svg2fcm -s V -l version     -d 'Show version and exit'

# Positional argument: complete .svg files.
# Fish auto-suggests files anyway; this scopes the suggestion to .svg
# when the cursor isn't on a flag value.
complete -c svg2fcm -k -F -n 'not __fish_seen_argument -s o -l output' \
    -a "(__fish_complete_suffix .svg)"
