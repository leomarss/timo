# Recorded by assets/demo/record.sh, which sets up the demo vault. Run that, not this file.
Output assets/demo-light.gif

Set Shell "bash"
Set FontSize 20
Set Width 1260
Set Height 440
Set Padding 28
Set TypingSpeed 70ms
Set Theme { "name": "timo-light", "background": "#f6f8fc", "foreground": "#0f1626", "cursor": "#2f6bf0", "selection": "#dbe4f5", "black": "#0f1626", "brightBlack": "#8a94a8", "red": "#d6334a", "brightRed": "#e04e63", "green": "#178a52", "brightGreen": "#1f9d5f", "yellow": "#b7791f", "brightYellow": "#c98a2b", "blue": "#2f6bf0", "brightBlue": "#4f8cff", "magenta": "#7c4ddb", "brightMagenta": "#9466f0", "cyan": "#0e8ac7", "brightCyan": "#1fa0de", "white": "#4a5468", "brightWhite": "#0f1626" }

Hide
Type "export PS1='\[\e[38;2;47;107;240m\]$\[\e[0m\] ' FZF_DEFAULT_OPTS='--color=light,bg+:#e3eaf8,hl:#2f6bf0,hl+:#2f6bf0,pointer:#2f6bf0,prompt:#2f6bf0,info:#8a94a8,border:#c9d2e3'" Enter
Type "bash assets/demo/wait.sh" Enter
Wait+Screen@40s /READY/
Type "clear" Enter
Show

Sleep 600ms
Type "timo github" Sleep 400ms Enter
Sleep 2.5s
Type "clear" Enter

Type "timo" Sleep 400ms Enter
Sleep 1.2s
Type "cloud" Sleep 1.2s Enter
Sleep 3s
Type "clear" Enter

# off screen: wait for a fresh 30-second window, so the new account's code shows plenty of time left
Hide
Type "bash assets/demo/wait.sh" Enter
Wait+Screen@40s /READY/
Type "clear" Enter
Show

Type "timo --add" Sleep 400ms Enter
Sleep 1s
Type "y"
Sleep 800ms
Type@20ms "JBSW Y3DP EHPK 3PXP"
Sleep 300ms Enter
Sleep 700ms
Type "Proton" Sleep 300ms Enter
Sleep 500ms
Type "you@proton.me" Sleep 300ms Enter
Sleep 4s
