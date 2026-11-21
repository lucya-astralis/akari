# Akari OS: the powerlevel10k look. p10k's own "lean" style, in Facet's
# colours: the accent violet for the prompt character and the folder you
# are in, quiet greys for the rest. Your own ~/.p10k.zsh replaces this file.

source /usr/share/powerlevel10k/config/p10k-lean.zsh

typeset -g POWERLEVEL9K_MODE=nerdfont-complete
typeset -g POWERLEVEL9K_PROMPT_ADD_NEWLINE=true

# left: where you are and git; right: what the last command did
typeset -g POWERLEVEL9K_LEFT_PROMPT_ELEMENTS=(os_icon context dir vcs newline prompt_char)

# the Akari OS mark in front: a character on U+F0000 from the font "Akari Symbols",
# which the web terminal (and Linux apps here) have; elsewhere, over ssh, a plain diamond
if [[ $TERM_PROGRAM == "Akari Terminal" ]]; then
  typeset -g POWERLEVEL9K_OS_ICON_CONTENT_EXPANSION=$'\U000F0000'
else
  typeset -g POWERLEVEL9K_OS_ICON_CONTENT_EXPANSION='◆'
fi
typeset -g POWERLEVEL9K_OS_ICON_FOREGROUND=141
typeset -g POWERLEVEL9K_RIGHT_PROMPT_ELEMENTS=(status command_execution_time background_jobs virtualenv time)

# user@host: always, quiet; violet over ssh, so you know where you are
typeset -g POWERLEVEL9K_CONTEXT_TEMPLATE='%n@%m'
typeset -g POWERLEVEL9K_CONTEXT_FOREGROUND=243
typeset -g POWERLEVEL9K_CONTEXT_REMOTE_FOREGROUND=141
typeset -g POWERLEVEL9K_CONTEXT_{DEFAULT,SUDO}_CONTENT_EXPANSION='%n@%m'
typeset -g POWERLEVEL9K_CONTEXT_ROOT_FOREGROUND=203

typeset -g POWERLEVEL9K_DIR_FOREGROUND=255
typeset -g POWERLEVEL9K_DIR_SHORTENED_FOREGROUND=245
typeset -g POWERLEVEL9K_DIR_ANCHOR_FOREGROUND=141
typeset -g POWERLEVEL9K_DIR_ANCHOR_BOLD=true

typeset -g POWERLEVEL9K_VCS_CLEAN_FOREGROUND=114
typeset -g POWERLEVEL9K_VCS_MODIFIED_FOREGROUND=221
typeset -g POWERLEVEL9K_VCS_UNTRACKED_FOREGROUND=117

typeset -g POWERLEVEL9K_PROMPT_CHAR_OK_{VIINS,VICMD,VIVIS,VIOWR}_FOREGROUND=141
typeset -g POWERLEVEL9K_PROMPT_CHAR_ERROR_{VIINS,VICMD,VIVIS,VIOWR}_FOREGROUND=203

typeset -g POWERLEVEL9K_TIME_FOREGROUND=243
typeset -g POWERLEVEL9K_TIME_FORMAT='%D{%H:%M}'
typeset -g POWERLEVEL9K_COMMAND_EXECUTION_TIME_FOREGROUND=243

(( ! $+functions[p10k] )) || p10k reload
