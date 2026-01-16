# CMakeLists.txt for USBridge Host firmware (Pico 2W)

cmake_minimum_required(VERSION 3.13)

# Set the board type to Pico 2W (RP2350 with WiFi)
set(PICO_BOARD pico2_w)

# Initialize the Pico SDK
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(usbridge_host C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Initialize the SDK
pico_sdk_init()

# =============================================================================
# Blink Test (for verifying toolchain)
# =============================================================================
add_executable(blink_test
    blink_test.c
)

target_link_libraries(blink_test
    pico_stdlib
    pico_cyw43_arch_none
)

pico_enable_stdio_usb(blink_test 1)
pico_enable_stdio_uart(blink_test 0)
pico_add_extra_outputs(blink_test)

# =============================================================================
# USBridge Host Firmware
# =============================================================================
add_executable(usbridge_host
    main.c
    usbridge_host.c
    usb_hid.c
    usb_descriptors.c
    usb_stdio.c
    usb_reset.c
)

# Include our btstack_config.h and TinyUSB config
target_include_directories(usbridge_host PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
)

# Disable CYW43 lwIP (we're BLE only, no WiFi)
target_compile_definitions(usbridge_host PRIVATE
    CYW43_LWIP=0
)

# Generate GATT header from .gatt file
pico_btstack_make_gatt_header(usbridge_host PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/usbridge_host.gatt
)

# Link required libraries
target_link_libraries(usbridge_host
    pico_stdlib
    pico_cyw43_arch_threadsafe_background
    pico_btstack_ble
    pico_btstack_cyw43
    tinyusb_device
)

# Use CDC for stdio output (part of our composite USB device)
pico_enable_stdio_usb(usbridge_host 0)
pico_enable_stdio_uart(usbridge_host 0)

# Create UF2 output
pico_add_extra_outputs(usbridge_host)
