/* ════════════════════════════════════════════════════════════════════════
   Fair Code - held-out column rows for the proxy check (issues #801-#803)

   Renders "file + column name" rows into a container (add/remove, any number
   of columns, .csv/.tsv/.json/.xlsx) and collects them into the specs that
   FairCodeProfiler.buildHeldOut() turns into a {column: values} map - the
   browser counterpart of repeating --proxy-hints-with PATH=COLUMN. Shared by
   the single-dataset and compare views. Column and join key are separate
   inputs (#822/#869), so a held-out column whose name contains a colon
   (e.g. race:self_reported) needs no escaping here - unlike the CLI's
   PATH=COLUMN:KEY string form.
   ════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var ACCEPT = '.csv,.tsv,.json,.xlsx,text/csv,application/json,' +
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

  // `getEncoding` (optional) returns the text-encoding choice of the page's picker (#857).
  function init(container, addBtn, label, getEncoding) {
    function addRow() {
      var row = document.createElement('div');
      row.className = 'heldout-row';
      var fileLabel = document.createElement('label');
      fileLabel.textContent = 'File ';
      var file = document.createElement('input');
      file.type = 'file';
      file.accept = ACCEPT;
      file.setAttribute('aria-label', label + ' file');
      fileLabel.appendChild(file);
      var colLabel = document.createElement('label');
      colLabel.textContent = 'Column ';
      var col = document.createElement('input');
      col.type = 'text';
      col.className = 'threshold-input';
      col.placeholder = 'e.g. race or race:self_reported';
      col.autocomplete = 'off';
      col.setAttribute('aria-label', label + ' column name');
      colLabel.appendChild(col);
      var keyLabel = document.createElement('label');
      keyLabel.textContent = 'Join key (optional) ';
      var key = document.createElement('input');
      key.type = 'text';
      key.className = 'threshold-input';
      key.placeholder = 'e.g. id';
      key.autocomplete = 'off';
      key.setAttribute('aria-label', label + ' join key column (optional)');
      keyLabel.appendChild(key);
      var normLabel = document.createElement('label');
      normLabel.textContent = 'Normalise key ';
      var norm = document.createElement('input');
      norm.type = 'checkbox';
      norm.setAttribute('aria-label', label + ' normalise join key (ignore case, spaces, leading zeros)');
      normLabel.appendChild(norm);
      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'heldout-remove';
      remove.textContent = '✕';
      remove.setAttribute('aria-label', 'Remove this ' + label + ' column');
      remove.addEventListener('click', function () {
        if (container.children.length > 1) container.removeChild(row);
        else { file.value = ''; col.value = ''; key.value = ''; norm.checked = false; }
      });
      row.appendChild(fileLabel);
      row.appendChild(colLabel);
      row.appendChild(keyLabel);
      row.appendChild(normLabel);
      row.appendChild(remove);
      container.appendChild(row);
    }
    addRow();
    addBtn.addEventListener('click', addRow);

    // Resolves to [{name, column, key?, data, file}] for every row the user filled in;
    // throws if a row has only one of file/column. [] means "no held-out test".
    async function collect() {
      var specs = [];
      var rows = Array.prototype.slice.call(container.children);
      for (var i = 0; i < rows.length; i++) {
        var inputs = rows[i].querySelectorAll('input');
        var file = inputs[0].files && inputs[0].files[0];
        var column = inputs[1].value.trim();
        var key = inputs[2].value.trim();
        var normalize = !!inputs[3].checked;
        if (!file && !column) continue;
        if (!file || !column) throw new Error('each held-out row needs both a file and a column name');
        var data;
        if (/\.xlsx$/i.test(file.name)) data = await file.arrayBuffer();
        else if (getEncoding && window.FairCodeProfiler && window.FairCodeProfiler.decodeText) {
          data = window.FairCodeProfiler.decodeText(await file.arrayBuffer(), getEncoding()).text;
        } else data = await file.text();
        specs.push({ name: file.name, column: column, key: key || undefined, normalize: (key && normalize) || undefined, data: data, file: file });
      }
      return specs;
    }

    function reset() {
      while (container.children.length > 0) {
        container.removeChild(container.children[0]);
      }
      container.innerHTML = '';
      addRow();
    }

    return { collect: collect, reset: reset };
  }


  window.FairCodeHeldOut = { init: init };
})();
