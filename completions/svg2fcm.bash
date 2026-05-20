# Bash completion for svg2fcm.
#
# Install: source this file from your ~/.bashrc, e.g.
#     . "$HOME/.local/share/svg2fcm/completions/svg2fcm.bash"
# Or system-wide:
#     sudo cp svg2fcm.bash /etc/bash_completion.d/svg2fcm

_svg2fcm() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="-h --help -o --output -v --verbose -n --no-group --fix-viewbox --no-viewbox-fix -V --version"

    # After -o/--output, complete file or directory paths.
    case "${prev}" in
        -o|--output)
            COMPREPLY=( $(compgen -f -- "${cur}") )
            return 0
            ;;
    esac

    # Flag completion when the current word starts with a dash.
    if [[ ${cur} == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    # Otherwise complete .svg input files (and directories so users can
    # tab into subfolders).
    COMPREPLY=( $(compgen -f -X '!*.svg' -- "${cur}") $(compgen -d -- "${cur}") )
    return 0
}

complete -F _svg2fcm svg2fcm
