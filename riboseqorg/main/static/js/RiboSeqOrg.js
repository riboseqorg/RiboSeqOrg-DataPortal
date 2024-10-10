function buildURL(item) {
  item.href = baseurl + window.location.href;
  return true;
}

$(function () {
  const x = new URLSearchParams(window.location.search);
  const vals = [];
  const filters = [];
  for (const [key, value] of x) {
    vals.push(value);
    const filter =
      "<li>" +
      value +
      " <bold style='color:red'><a class='key' data-value='" +
      key +
      "=" +
      value +
      "'>×</a></bold></li>";
    if (filters.indexOf(filter) == -1) {
      filters.push(filter);
    }
  }
  if (vals.length != 0) {
    const filters_str =
      "<ul class='key2'><li>Filters:</li>" + filters.join(" ") + "</ul>";
    $("a.sidenav-link").each(function () {
      const a_val = $(this).html().trim();
      if (vals.indexOf(a_val) > -1) {
        $(this).css("color", "red");
      }
    });

    $("#filters").html(filters_str);
  }
});

$(document).ready(function () {
  $(".key").click(function () {
    // const to_remove = $(this).html();
    const to_remove = $(this).data("value");
    const vals = [];
    $(".key").each(function () {
      const a_val = $(this).data("value");
      if (a_val != to_remove) {
        vals.push(a_val);
      }
    });
    const new_url = window.location.pathname + "?" + vals.join("&");
    window.location.href = new_url;
    // window.open(new_url);
  });
});
