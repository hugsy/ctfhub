var isKeyPressed = {};





function triggerShortcutEvent()
{
    for(let key in shortcutFunctionTable)
    {
        let keys = key.split("+");
        let executeEvent = true;
        for(let i=0; i<keys.length; i++)
        {
            if(!isKeyPressed[keys[i]])
            {
                executeEvent = false;
                break;
            }
        }
        if(executeEvent)
        {
            shortcutFunctionTable[key]();
        }
    }
}


document.onkeydown = (keyDownEvent) =>
{
    isKeyPressed[keyDownEvent.key] = true;
    triggerShortcutEvent();
};


document.onkeyup = (keyUpEvent) =>
{
    //keyUpEvent.preventDefault();
    isKeyPressed[keyUpEvent.key] = false;
};
