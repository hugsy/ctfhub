function generate_random_string(length = 12)
{
    let charset = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let str = '';
    for (let i = 0; i < length; i++)
        str += charset.charAt(Math.floor(Math.random() * charset.length));

    return str;
}
