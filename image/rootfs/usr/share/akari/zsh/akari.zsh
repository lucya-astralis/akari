# Akari OS: the zsh every account starts with: oh-my-zsh with powerlevel10k.
# Sourced from ~/.zshrc; this file comes with the image, your own lines go
# into ~/.zshrc. Before the `source` line there you can set:
#   AKARI_QUIET=1                 no fastfetch when a terminal opens
#   AKARI_THEME=robbyrussell      another oh-my-zsh theme instead of p10k
#   AKARI_PLUGINS=(git z)         other oh-my-zsh plugins
# `p10k configure` writes ~/.p10k.zsh, which then wins over Akari's look.

# --- oh-my-zsh, read-only in /usr/share, its cache in the home ---
export ZSH=/usr/share/oh-my-zsh
ZSH_CUSTOM=$ZSH/custom
ZSH_CACHE_DIR=${XDG_CACHE_HOME:-$HOME/.cache}/oh-my-zsh
ZSH_COMPDUMP=$ZSH_CACHE_DIR/zcompdump-$ZSH_VERSION
[[ -d $ZSH_CACHE_DIR/completions ]] || mkdir -p $ZSH_CACHE_DIR/completions
DISABLE_AUTO_UPDATE=true
ZSH_DISABLE_COMPFIX=true
zstyle ':omz:update' mode disabled

ZSH_THEME=${AKARI_THEME-powerlevel10k/powerlevel10k}
if (( ${+AKARI_PLUGINS} )); then
  plugins=($AKARI_PLUGINS)
else
  plugins=(git colored-man-pages extract z zsh-autosuggestions zsh-syntax-highlighting)
fi

# --- powerlevel10k: never the wizard on its own, gitstatusd from the image ---
typeset -g POWERLEVEL9K_DISABLE_CONFIGURATION_WIZARD=true
typeset -g GITSTATUS_CACHE_DIR=/usr/share/powerlevel10k/gitstatus/usrbin
typeset -g GITSTATUS_AUTO_INSTALL=0

HISTFILE=~/.zsh_history
HISTSIZE=20000
SAVEHIST=20000
setopt hist_ignore_dups hist_ignore_space share_history extended_history
setopt autocd interactive_comments no_beep

# a new terminal (or an ssh login) greets with fastfetch, before the prompt draws
if [[ -o interactive && -o login && -z $AKARI_QUIET ]] && \
   [[ $TERM_PROGRAM == "Akari Terminal" || -n $SSH_CONNECTION ]] && (( $+commands[fastfetch] )); then
  # in the desktop's accent colour: the terminal passes it on, ssh takes the last one used
  _akari_acc=${AKARI_ACCENT:-$(cat ~/.config/akari/accent 2>/dev/null)}
  if [[ $_akari_acc =~ '^#[0-9a-fA-F]{6}$' ]]; then
    _akari_acc="38;2;$((16#${_akari_acc:1:2}));$((16#${_akari_acc:3:2}));$((16#${_akari_acc:5:2}))"
    fastfetch --logo-color-1 "$_akari_acc" --color-keys "$_akari_acc"
  else
    fastfetch
  fi
  unset _akari_acc
fi

source $ZSH/oh-my-zsh.sh

if [[ $ZSH_THEME == powerlevel10k/powerlevel10k ]]; then
  if [[ -r ~/.p10k.zsh ]]; then
    source ~/.p10k.zsh
  else
    source /usr/share/akari/zsh/p10k-akari.zsh
  fi
fi

ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=243'
alias ll='ls -lah --color=auto' la='ls -A --color=auto'
