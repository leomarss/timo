# Recorded by assets/demo/record.sh, which sets up the demo vault. Run that, not this file.
Output assets/demo.gif

Set Shell "bash"
Set FontSize 20
Set Width 1260
Set Height 440
Set Padding 28
Set TypingSpeed 70ms
Set Theme { "name": "timo", "background": "#0f1626", "foreground": "#e6ebf5", "cursor": "#4f8cff", "selection": "#25324d", "black": "#0f1626", "brightBlack": "#5b6680", "red": "#ff6b7a", "brightRed": "#ff8a96", "green": "#4fd18b", "brightGreen": "#6fe0a3", "yellow": "#ffc857", "brightYellow": "#ffd77f", "blue": "#4f8cff", "brightBlue": "#7aa8ff", "magenta": "#b18cff", "brightMagenta": "#c7a9ff", "cyan": "#5cc8ff", "brightCyan": "#85d6ff", "white": "#c9d1e0", "brightWhite": "#ffffff" }

Hide
Type "export PS1='\[\e[38;2;79;140;255m\]$\[\e[0m\] ' FZF_DEFAULT_OPTS='--color=bg+:#1a2440,hl:#4f8cff,hl+:#7aa8ff,pointer:#4f8cff,prompt:#4f8cff,info:#5b6680'" Enter
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
