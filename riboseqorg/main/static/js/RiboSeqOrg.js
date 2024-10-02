function buildURL(item) {
        item.href = baseurl + window.location.href;
        return true;
};



$(function() {
        const x = new URLSearchParams(window.location.search);
        const vals = [];
        for (const [key, value] of x) {
                console.log(`${key}: ${value}`);
                vals.push(value);
        }
        $("a.sidenav-link").each(function() {
                const a_val = $(this).html().trim();
                if (vals.indexOf(a_val) > -1) {

                        $(this).css("background-color", "red");
                }
        });

});
