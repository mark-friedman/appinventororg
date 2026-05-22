/* 
 * The following javascript is used on the import courses admin page.
 */

$(document).ready(function() {

	// button triggers file selection window
	$('#import_upload_button').click(function() {
		$('#import_file_input').click();
	})

	// file was selected, parse it and preview it
	$('#import_file_input').change(function() {
		
		file = $(this)[0].files[0];
		
		reader = new FileReader();

		reader.onload = function(e) {

			$(".loading-icon").addClass("visible");

			$.post("/admin/importcourses", {
				s_File_Contents : reader.result,
			})
			.done(function(data, status) {
				$(".loading-icon").removeClass("visible");
				location.reload(true);
			})
			.fail(function(xhr, status, error) {
				$(".loading-icon").removeClass("visible");
				console.error("Import failed:", status, error, xhr.status, xhr.responseText);
				alert("Import failed (" + xhr.status + "): " + (error || "Unknown Error") + "\nCheck browser console and server logs for details.");
			});
		}
		reader.readAsText(file);
	});
	
});