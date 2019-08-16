exports.handler = function(event, context, callback) {
    console.log("Spam Filter Start");
    
    var badSenders = ["Amazon.com <store-news@amazon.com>", "Amazon.com <store_news@amazon.com>"]
    var sesNotification = event.Records[0].ses;
    console.log("SES Notification:\n", JSON.stringify(sesNotification, null, 2));
    
    // Iterate over the headers
    for (var index in sesNotification.mail.headers) {
        var header = sesNotification.mail.headers[index];
        // Examine the header values
        if (header.name === "From") {
            console.log("From: " + header.value);
            if (badSenders.indexOf(header.value) > -1) {
                console.log("Found bad sender: " + header.value);
                callback(null, {'disposition':'STOP_RULE'});   
                return;
            }   
        }
    }
    // Stop processing the rule if the header value wasn't found
    callback(null, null);
    return; 
};