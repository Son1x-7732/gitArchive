# ==========================================
#  NIX@VOID ZSH CONFIG
# ==========================================

# --- 1. KITTY BORDER LOCK & INSTANT PROMPT ---
# Lock Kitty top border text
DISABLE_AUTO_TITLE="true"
echo -en "\e]0;kitty\a"

# Enables the prompt to appear instantly while plugins load in the background
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# --- 2. ENVIRONMENT & SETTINGS ---
export EDITOR='micro'
export VISUAL='micro'
export TERMINAL='kitty'
export MANPAGER="sh -c 'col -bx | bat -l man -p'"
export PATH="$HOME/.local/bin:$PATH"

# History Settings
HISTFILE=~/.zsh_history
HISTSIZE=10000
SAVEHIST=10000
setopt APPEND_HISTORY          
setopt INC_APPEND_HISTORY      
setopt HIST_IGNORE_DUPS        
setopt HIST_FIND_NO_DUPS       
setopt SHARE_HISTORY           
setopt BANG_HIST               

# --- AUTOCOMPLETION ENGINE ---
autoload -Uz compinit
compinit
zstyle ':completion:*' menu select

# --- 3. PLUGINS ---

# A. Powerlevel10k Theme (Local Clone)
source ~/powerlevel10k/powerlevel10k.zsh-theme

# B. Fish-like Syntax Highlighting
source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh

# C. Ghost History (Autosuggestions)
source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=242'

# D. History Substring Search
source /usr/share/zsh/plugins/zsh-history-substring-search/zsh-history-substring-search.zsh

# E. "Command Not Found" handler
source /usr/share/doc/pkgfile/command-not-found.zsh

# F. FZF Integration
[ -f /usr/share/fzf/key-bindings.zsh ] && source /usr/share/fzf/key-bindings.zsh
[ -f /usr/share/fzf/completion.zsh ] && source /usr/share/fzf/completion.zsh

# --- 4. KEYBINDINGS ---
bindkey -e 
bindkey '^[[A' history-substring-search-up
bindkey '^[[B' history-substring-search-down

# --- 5. HELPER FUNCTIONS ---
function backup() {
    cp -iv "$1" "$1.bak"
}

# --- 6. ALIASES ---

# > Navigation
alias ..='cd ..'
alias ...='cd ../..'
alias ll='eza --icons --git --long --header --group-directories-first'
alias ls='eza --icons --git'
alias lt='eza --icons --tree'

# > Package Management (Pacman)
alias update='sudo pacman -Syu'
alias install='sudo pacman -S'
alias search='pacman -Ss'
alias delete='sudo pacman -Rns'
alias cleanup='sudo pacman -Rns $(pacman -Qtdq)'
alias cleancache='sudo pacman -Sc'
alias fixpacman="sudo rm /var/lib/pacman/db.lck"
alias mirror="sudo cachyos-rate-mirrors"
alias findpkg="pacman -Qs"
alias rip="expac --timefmt='%Y-%m-%d %T' '%l\t%n %v' | sort | tail -200 | nl"

# > Config Shortcuts
alias zshconf="micro ~/.zshrc"
alias kittyconf="micro ~/.config/kitty/kitty.conf"
alias hyprconf="micro ~/.config/hypr/hyprland.conf"
alias niriconf="micro ~/.config/niri/config.kdl"
alias reload="source ~/.zshrc"
alias waybarjson="micro ~/.config/waybar/config.jsonc"
alias waybarcss="micro ~/.config/waybar/style.css"

# > Utils
alias tb='nc termbin.com 9999'
alias gstatus='gh status'
alias gclone='gh repo clone'
alias gcreate='gh repo create'
alias fixfonts="fc-cache -fv"

# > Safety
alias cp="cp -iv"
alias mv="mv -iv"
alias rm="rm -v"

# --- 7. LOAD P10K LAYOUT ---
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

# --- 8. BARE REPO DOTFILES ---
alias config='/usr/bin/git --git-dir=/home/nix/.dotfiles/ --work-tree=/home/nix'

# Note: You previously preferred a manual dotsync instead of this automated one to prevent 
# pushing broken configs or sensitive data. If you wish to use the automated version, uncomment it.
# dotsync() {
#    /usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME add -u
#    /usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME commit -m "Update: $(date)"
#    /usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME push
# }
