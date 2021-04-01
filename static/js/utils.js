function generate_random_string(length = 12)
{
    let charset = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let str = '';
    for (let i = 0; i < length; i++)
        str += charset.charAt(Math.floor(Math.random() * charset.length));

    return str;
}

function toggle_input_password_visibility()
{
    for(let r of document.getElementsByClassName("reveal") )
    {
        if (r.type === "password")
            r.type = "text";

        else if (r.type === "text")
            r.type = "password";
    }
}

function generate_random_color(number)
{
    const hue = number * 137.508; // use golden angle approximation
    return `hsl(${hue},50%,75%)`;
}


function timeuntil(datetime)
{
    const end = new Date(datetime).getTime();
    const now = new Date().getTime();

    const offset = end - now;
    if (offset < 0)
        return "Finished";

    let days    = Math.floor(offset / (1000 * 60 * 60 * 24));
    let hours   = Math.floor((offset % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    let minutes = Math.floor((offset % (1000 * 60 * 60)) / (1000 * 60));
    let seconds = Math.floor((offset % (1000 * 60)) / 1000);

    var res = "";
    if (days)
        res += `${days}d `;
    res += `${hours}h ${minutes}m ${seconds}s left`;
    return res;
}


// function get_random_int(max)
// {
//     return Math.floor(Math.random() * Math.floor(max));
// }

// function generate_random_rgba()
// {
//     return `rgba(${get_random_int(256)}, ${get_random_int(256)}, ${get_random_int(256)}, 0.2)`;
// }

// function generate_random_rgb()
// {
//     return `rgb(${get_random_int(256)}, ${get_random_int(256)}, ${get_random_int(256)})`;
// }