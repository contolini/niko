$(document).ready(function() {

  var classSwitch = function(node) {
    $(node).addClass('selected')
          .siblings().removeClass('selected');

    return node;
  };

  $('.tab').on('click', function() {
    var timeVal;
    if (!($(this).hasClass === 'selected')) {
      timeVal = $(this).attr('id');
      classSwitch($(this)).find('#date-input').attr('value', timeVal);

      Niko.changeGreeting(timeVal);
    }
  });

  $('.mood-face').on('click', function() {
    var moodVal,
        $this = $(this);
    if (!($this.hasClass === 'selected')) {
      moodVal = $this.attr('data-value');
      $("#mood-input").val(moodVal);
      classSwitch($this);
    }
  });
});

Niko = {
  changeGreeting: function(timeVal) {
    if (timeVal === 'today') {
      $('#greeting').html("How's it going");
    }
    else if (timeVal === 'yesterday') {
      $('#greeting').html("How was yesterday");
    }
  }
};
