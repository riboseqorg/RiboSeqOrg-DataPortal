function buildURL(item) {
  item.href = baseurl + window.location.href;
  return true;
}

$(function () {
  const x = new URLSearchParams(window.location.search);
  const vals = [];
  const filters = [];
  for (const [key, value] of x) {
    console.log(`${key}: ${value}`);
    vals.push(value);
    const filter = key + "=" + value;
    if (filters.indexOf(filter) == -1) {
      filters.push(filter);
    }
  }
  const filters_str = "Filters: " + filters.join("&");
  $("a.sidenav-link").each(function () {
    const a_val = $(this).html().trim();
    if (vals.indexOf(a_val) > -1) {
      $(this).css("color", "red");
    }
  });

  $("#filters").html(filters_str);
});
