#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>

@interface AppDelegate : NSObject <NSApplicationDelegate, WKNavigationDelegate>
@property (strong, nonatomic) NSWindow *window;
@property (strong, nonatomic) WKWebView *webView;
@property (strong, nonatomic) NSTask *serverTask;
@end

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [self startBackendServerIfNeeded];

    NSRect frame = NSMakeRect(0, 0, 1280, 840);
    NSUInteger style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                       NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable;
    self.window = [[NSWindow alloc] initWithContentRect:frame
                                              styleMask:style
                                                backing:NSBackingStoreBuffered
                                                  defer:NO];
    [self.window setTitle:@"Anki Studio 2.0 — FSRS-5 & AI Active Recall Studio"];
    [self.window center];

    WKWebViewConfiguration *config = [[WKWebViewConfiguration alloc] init];
    self.webView = [[WKWebView alloc] initWithFrame:frame configuration:config];
    self.webView.navigationDelegate = self;
    [self.window setContentView:self.webView];
    [self.window makeKeyAndOrderFront:nil];

    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(450 * NSEC_PER_MSEC)), dispatch_get_main_queue(), ^{
        NSURL *url = [NSURL URLWithString:@"http://127.0.0.1:4390"];
        [self.webView loadRequest:[NSURLRequest requestWithURL:url]];
    });
}

- (void)startBackendServerIfNeeded {
    NSBundle *bundle = [NSBundle mainBundle];
    NSString *bundlePath = [bundle bundlePath];
    NSString *projectRoot = [bundlePath stringByDeletingLastPathComponent];
    NSString *srcDir = [projectRoot stringByAppendingPathComponent:@"src"];

    self.serverTask = [[NSTask alloc] init];
    self.serverTask.executableURL = [NSURL fileURLWithPath:@"/usr/bin/python3"];
    self.serverTask.arguments = @[@"-m", @"anki_studio.service.studio_server"];
    NSMutableDictionary *env = [[[NSProcessInfo processInfo] environment] mutableCopy];
    env[@"PYTHONPATH"] = srcDir;
    self.serverTask.environment = env;
    @try {
        [self.serverTask launchAndReturnError:nil];
    } @catch (NSException *exception) {
    }
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    if (self.serverTask && self.serverTask.isRunning) {
        [self.serverTask terminate];
    }
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    return YES;
}

@end

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        AppDelegate *delegate = [[AppDelegate alloc] init];
        [app setDelegate:delegate];
        [app activateIgnoringOtherApps:YES];
        [app run];
    }
    return 0;
}
