using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace ASTCReproduction
{
    public static class BenchmarkRunner
    {
        [Serializable] public sealed class AssetEntry { public string path; }
        [Serializable] public sealed class MetadataEntry { public string asset; public string backup; }
        [Serializable] public sealed class RunConfig
        {
            public AssetEntry[] assets;
            public AssetEntry[] warmup;
            public string output;
            public string backupDirectory;
            public string cacheDirectory;
            public string runId;
            public bool captureReferences;
        }
        [Serializable] public sealed class ImportResult
        {
            public string asset;
            public string run_id;
            public double import_wall_ms;
            public bool success;
            public string error;
            public string texture_type;
            public string pre_import_android_format;
            public bool pre_import_android_override;
            public bool srgb;
            public bool mipmaps;
            public int width;
            public int height;
            public string format;
            public string texture_dimension;
            public string reference_directory;
        }

        private static bool s_CaptureReferences;

        private const ImportAssetOptions ReimportOptions = ImportAssetOptions.ForceUpdate
            | ImportAssetOptions.ForceSynchronousImport | ImportAssetOptions.DontDownloadFromCacheServer;

        private static void Required(string name, params object[] args)
        {
            var method = typeof(EditorApplication).GetMethod(name, BindingFlags.Public | BindingFlags.Static);
            if (method == null) throw new MissingMethodException("Required native API " + name);
            method.Invoke(null, args);
        }

        private static void ConfigureQuality()
        {
            Required("SetASTCOptimizationEnabled", true);
            Required("SetAstc3rdRdoSettings", false, 0.5f, 256);
            Required("SetAstcQualityThresholds", 30f, 21f, 3.2f, 9f);
            Required("SetAstcBlackPixelPsnrPolicy", 0.4f, 35f, 0.8f, 37f);
            Required("SetAstcSizeFirstMinSideForLargeTexture", 512);
            Required("SetAstcRdoRefineMinPsnrMarginDb", 0f);
            Required("SetAstcDebugEnabled", s_CaptureReferences);
        }

        private static void ImportOptions(string path, ref int useThirdParty, ref int packNormal)
        {
            ConfigureQuality();
            useThirdParty = 1;
            packNormal = 0;
        }

        private static void RegisterEncoder()
        {
            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                var type = assembly.GetType("ASTCCustom", false);
                if (type == null) continue;
                var setter = type.GetMethod("SetUseOptimizeInterface", BindingFlags.Public | BindingFlags.Static);
                if (setter == null) throw new MissingMethodException("ASTCCustom.SetUseOptimizeInterface");
                setter.Invoke(null, new object[] { true });
                return;
            }
            throw new TypeLoadException("Project ASTCCustom backend was not loaded");
        }

        private static string HashFile(string path)
        {
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(path))).Replace("-", "").ToLowerInvariant();
        }

        private static ImportResult ImportOne(RunConfig config, AssetEntry asset)
        {
            var row = new ImportResult { asset = asset.path, run_id = config.runId };
            string meta = asset.path + ".meta";
            string backupName;
            using (var sha = SHA256.Create())
                backupName = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(asset.path)))
                    .Replace("-", "").ToLowerInvariant() + ".meta";
            string backup = Path.Combine(config.backupDirectory, backupName);
            var timer = new Stopwatch();
            try
            {
                var importer = AssetImporter.GetAtPath(asset.path) as TextureImporter;
                if (importer == null) throw new InvalidOperationException("No TextureImporter");
                Directory.CreateDirectory(Path.GetDirectoryName(backup));
                if (!File.Exists(backup))
                    File.Copy(meta, backup);
                else if (HashFile(meta) != HashFile(backup))
                {
                    string expected = backup + ".expected.sha256";
                    if (!File.Exists(expected) || HashFile(meta) != File.ReadAllText(expected).Trim())
                        throw new IOException("Metadata changed since benchmark last wrote it: " + meta);
                }
                var metadata = new MetadataEntry { asset = asset.path, backup = backupName };
                File.AppendAllText(Path.Combine(config.backupDirectory, "index.jsonl"),
                    JsonUtility.ToJson(metadata) + Environment.NewLine);
                row.texture_type = importer.textureType.ToString();
                row.srgb = importer.sRGBTexture;
                row.mipmaps = importer.mipmapEnabled;
                var android = importer.GetPlatformTextureSettings("Android");
                row.pre_import_android_format = android.format.ToString();
                row.pre_import_android_override = android.overridden;
                android.name = "Android";
                android.overridden = true;
                android.format = TextureImporterFormat.ASTC_8x8;
                android.textureCompression = TextureImporterCompression.Compressed;
                android.crunchedCompression = false;
                importer.SetPlatformTextureSettings(android);
                AssetDatabase.WriteImportSettingsIfDirty(asset.path);
                File.WriteAllText(backup + ".expected.sha256", HashFile(meta));
                var importStartedUtc = DateTime.UtcNow;
                timer.Start();
                AssetDatabase.ImportAsset(asset.path, ReimportOptions);
                timer.Stop();
                if (s_CaptureReferences)
                {
                    string matched = null;
                    foreach (var directory in Directory.GetDirectories("ASTC_Cache"))
                    {
                        string original = Path.Combine(directory, "original.png");
                        if (!File.Exists(original) || File.GetLastWriteTimeUtc(original) < importStartedUtc)
                            continue;
                        if (matched != null)
                            throw new IOException("More than one reference image was exported for " + asset.path);
                        matched = Path.GetFullPath(directory);
                    }
                    if (matched == null) throw new IOException("No reference image was exported for " + asset.path);
                    row.reference_directory = matched;
                }
                var texture = AssetDatabase.LoadAssetAtPath<Texture>(asset.path);
                if (texture == null) throw new InvalidOperationException("No imported Texture");
                row.width = texture.width;
                row.height = texture.height;
                row.texture_dimension = texture.dimension.ToString();
                if (texture is Texture2D)
                    row.format = ((Texture2D)texture).format.ToString();
                else if (texture is Cubemap)
                    row.format = ((Cubemap)texture).format.ToString();
                else
                    throw new InvalidOperationException("Unsupported imported texture dimension " + texture.dimension);
                row.success = true;
            }
            catch (Exception error) { row.error = error.ToString(); }
            finally
            {
                timer.Stop();
                row.import_wall_ms = timer.Elapsed.TotalMilliseconds;
            }
            return row;
        }

        public static void Run()
        {
            int exitCode = 0;
            try
            {
                var config = JsonUtility.FromJson<RunConfig>(File.ReadAllText(Environment.GetEnvironmentVariable("ASTC_BENCHMARK_CONFIG")));
                s_CaptureReferences = false;
                if (EditorUserBuildSettings.activeBuildTarget != BuildTarget.Android)
                    throw new InvalidOperationException("Benchmark requires Android");
                if (Directory.Exists(config.cacheDirectory)) throw new IOException("Cache namespace already exists");
                RegisterEncoder();
                ConfigureQuality();
                EditorApplication.OnImportAssetOption = ImportOptions;
                var thresholds = new object[] { 0f, 0f, 0f, 0f };
                Required("GetAstcQualityThresholds", thresholds);
                if ((float)thresholds[0] != 30f || (float)thresholds[1] != 21f
                    || (float)thresholds[2] != 3.2f || (float)thresholds[3] != 9f)
                    throw new InvalidOperationException("Native quality readback mismatch");
                Required("SetAstcParameterCacheTableDirectory", config.cacheDirectory + "-warmup");
                foreach (var asset in config.warmup)
                    if (!ImportOne(config, asset).success) throw new InvalidOperationException("Warmup import failed: " + asset.path);
                Required("SetAstcParameterCacheTableDirectory", config.cacheDirectory);
                s_CaptureReferences = config.captureReferences;
                string nativeLog = Environment.GetEnvironmentVariable("ASTC_BENCHMARK_LOG");
                if (File.Exists(nativeLog)) File.Delete(nativeLog);
                using (var writer = new StreamWriter(config.output, false))
                {
                    foreach (var asset in config.assets)
                    {
                        var row = ImportOne(config, asset);
                        writer.WriteLine(JsonUtility.ToJson(row));
                        writer.Flush();
                        if (!row.success) exitCode = 1;
                    }
                }
            }
            catch (Exception error) { UnityEngine.Debug.LogException(error); exitCode = 1; }
            finally { EditorApplication.Exit(exitCode); }
        }
    }
}
