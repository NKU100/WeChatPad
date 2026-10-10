import unittest

from scripts.ci.select_compatibility_window import matrix_entries, select_regression_targets


class SelectCompatibilityWindowTest(unittest.TestCase):
    def test_hosted_verified_profiles_count_toward_the_three_build_window(self):
        targets = [target("8.0.69", 3040), target("8.0.78", 3180),
                   target("8.0.79", 3200, "runtime-verified-hosted")]
        selected = select_regression_targets(targets, candidate_version_code=3220)
        self.assertEqual(["8.0.78", "8.0.79"], version_names(selected))
        self.assertLessEqual(len(selected) + 1, 3)

    def test_unknown_candidate_uses_only_the_two_newest_supported_predecessors(self):
        targets = [
            target("8.0.69", 3040),
            target("8.0.78", 3180),
            target("8.0.79", 3200),
            target("8.0.80", 3220, "static-verified"),
        ]

        selected = select_regression_targets(targets, candidate_version_code=3220)

        self.assertEqual(["8.0.78", "8.0.79"], version_names(selected))
        self.assertLessEqual(len(selected) + 1, 3)

    def test_registered_candidate_and_its_two_newest_predecessors_fit_the_window(self):
        targets = [
            target("8.0.60", 2800),
            target("8.0.69", 3040),
            target("8.0.78", 3180),
            target("8.0.79", 3200),
        ]

        selected = select_regression_targets(targets, candidate_version_code=3200)

        self.assertEqual(["8.0.69", "8.0.78", "8.0.79"], version_names(selected))
        self.assertLessEqual(len(selected), 3)

    def test_keeps_every_available_predecessor_when_fewer_than_two_are_supported(self):
        targets = [target("8.0.69", 3040)]

        selected = select_regression_targets(targets, candidate_version_code=3200)

        self.assertEqual(["8.0.69"], version_names(selected))

    def test_rejects_duplicate_version_codes_in_the_manifest(self):
        targets = [target("8.0.78", 3180, digest="a" * 64), target("8.0.78-alt", 3180, digest="b" * 64)]
        self.assertEqual(targets, select_regression_targets(targets, candidate_version_code=3200))

    def test_window_keeps_all_variants_from_three_most_recent_version_codes(self):
        targets = [target("8.0.69", 3040), target("8.0.78", 3180),
                   target("8.0.79", 3200, digest="a" * 64), target("8.0.79-repack", 3200, digest="b" * 64)]
        selected = select_regression_targets(targets, candidate_version_code=3200)
        self.assertEqual(["8.0.69", "8.0.78", "8.0.79", "8.0.79-repack"], version_names(selected))

    def test_unknown_same_version_candidate_includes_registered_variant(self):
        targets = [target("8.0.78", 3180), target("8.0.79", 3200)]
        self.assertEqual(targets, select_regression_targets(targets, candidate_version_code=3200))

    def test_matrix_contains_only_the_selected_profiles_and_their_integrity_fields(self):
        selected = select_regression_targets([
            target("8.0.69", 3040),
            target("8.0.78", 3180),
            target("8.0.79", 3200),
        ], candidate_version_code=3220)
        for entry, digest in zip(selected, ["c" * 64, "d" * 64]):
            entry["identity"]["apkSha256"] = digest
            entry["sourceUrl"] = f"https://dldir1v6.qq.com/weixin/android/{entry['identity']['versionName']}.apk"

        matrix = matrix_entries(selected)

        self.assertEqual(["8.0.78", "8.0.79"], [entry["version_name"] for entry in matrix])
        self.assertEqual(["c" * 64, "d" * 64], [entry["sha256"] for entry in matrix])
        self.assertTrue(all(entry["source_url"].startswith("https://dldir1v6.qq.com/weixin/android/") for entry in matrix))

    def test_matrix_rejects_a_selected_profile_without_an_apk_digest(self):
        missing_digest = target("8.0.69", 3040)
        missing_digest["identity"]["apkSha256"] = None
        with self.assertRaisesRegex(ValueError, "invalid APK SHA-256"):
            matrix_entries([missing_digest])

    def test_same_version_code_in_other_package_or_abi_does_not_change_window(self):
        targets = [target("8.0.78", 3180), target("8.0.79", 3200)]
        targets.append(target("other-8.0.99", 3200, package="org.example.other"))
        targets.append(target("other-abi-8.0.99", 3200, abi="x86_64"))
        selected = select_regression_targets(targets, 3220, app_id="wechat", package_name="com.tencent.mm", abi="arm64-v8a")
        self.assertEqual(["8.0.78", "8.0.79"], version_names(selected))


def target(version_name, version_code, verification_status="runtime-verified-local", package="com.tencent.mm", abi="arm64-v8a", digest=None):
    return {
        "identity": {
            "packageName": package,
            "versionName": version_name,
            "versionCode": version_code,
            "abi": abi,
            "apkSha256": digest or f"{version_code:064x}",
        },
        "verificationStatus": verification_status,
    }


def version_names(targets):
    return [target["identity"]["versionName"] for target in targets]


if __name__ == "__main__":
    unittest.main()
