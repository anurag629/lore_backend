# Customer Contact Validator And Report Generator
# Developed for COMP 1112 – Document Automation Using Python
# This program lets the user enter customer records, validates the input
# and prints a final summary report showing valid and invalid entries.

def showMenu():
    """Display the main menu options."""
    print()
    print("Customer Contact Validator")
    print("--------------------------")
    print("1. Add a new customer record")
    print("2. Show report and exit")
    print()


def getMenuChoice():
    """Get a valid menu choice from the user."""
    while True:
        choiceText = input("Enter your choice (1 or 2): ").strip()
        if choiceText == "1" or choiceText == "2":
            return choiceText
        else:
            print("Invalid choice. Please type 1 or 2 only.")


def getCustomerInput():
    """Collect raw customer details from the user."""
    print()
    print("Enter customer details")
    print("----------------------")
    customerName = input("Customer name: ").strip()
    customerEmail = input("Customer email: ").strip()
    customerPhone = input("Customer phone number: ").strip()
    return customerName, customerEmail, customerPhone


def validateCustomer(customerName, customerEmail, customerPhone):
    """
    Validate a single customer record.

    Returns:
        isValidCustomer (bool): True if all fields pass basic checks.
        errorMessage (str): Description of problems, or 'No errors found.'
    """
    isValidCustomer = True
    errorMessage = ""

    # Validate name
    if customerName == "":
        isValidCustomer = False
        errorMessage = errorMessage + "Name cannot be empty. "

    # Very simple email validation
    if "@" not in customerEmail or "." not in customerEmail:
        isValidCustomer = False
        errorMessage = errorMessage + "Email format is not correct. "

    # Validate phone
    if customerPhone == "":
        isValidCustomer = False
        errorMessage = errorMessage + "Phone number cannot be empty. "
    else:
        # Use try/except to show safe handling of conversion errors
        try:
            phoneNumber = int(customerPhone)
            # Check basic length rules after conversion succeeds
            phoneLength = len(str(phoneNumber))
            if phoneLength < 7 or phoneLength > 15:
                isValidCustomer = False
                errorMessage = errorMessage + "Phone number length is not realistic. "
        except ValueError:
            isValidCustomer = False
            errorMessage = errorMessage + "Phone number must contain digits only. "

    if errorMessage == "":
        errorMessage = "No errors found."

    return isValidCustomer, errorMessage


def addCustomerRecord(customerList):
    """Ask the user for customer details, validate and store them."""
    customerName, customerEmail, customerPhone = getCustomerInput()
    isValidCustomer, errorMessage = validateCustomer(
        customerName,
        customerEmail,
        customerPhone
    )

    # Each record is stored as a list:
    # [name, email, phone, isValid, errorMessage]
    customerRecord = [
        customerName,
        customerEmail,
        customerPhone,
        isValidCustomer,
        errorMessage
    ]

    customerList.append(customerRecord)
    print()
    print("Customer record added.")
    print("Validation result:", errorMessage)


def printReport(customerList):
    """Print a clear summary report of all stored customer records."""
    print()
    print("Customer Validation Report")
    print("--------------------------")

    if len(customerList) == 0:
        print("No customer records were entered.")
        return

    validCount = 0
    invalidCount = 0

    # First pass: count valid/invalid
    for customerRecord in customerList:
        if customerRecord[3]:
            validCount = validCount + 1
        else:
            invalidCount = invalidCount + 1

    print("Total customers entered:", len(customerList))
    print("Valid customers:", validCount)
    print("Invalid customers:", invalidCount)
    print()

    if invalidCount > 0:
        print("Details of invalid records:")
        print("---------------------------")
        recordNumber = 1
        for customerRecord in customerList:
            if not customerRecord[3]:
                print("Record number:", recordNumber)
                print("Name :", customerRecord[0])
                print("Email:", customerRecord[1])
                print("Phone:", customerRecord[2])
                print("Reason:", customerRecord[4])
                print()
            recordNumber = recordNumber + 1
    else:
        print("All customer records are valid. No problems were found.")


def main():
    """Main control loop for the application."""
    customerList = []

    while True:
        showMenu()
        menuChoice = getMenuChoice()

        if menuChoice == "1":
            addCustomerRecord(customerList)
        elif menuChoice == "2":
            printReport(customerList)
            print()
            print("Thank you for using the Customer Contact Validator.")
            break


# Start the program
if __name__ == "__main__":
    main()
