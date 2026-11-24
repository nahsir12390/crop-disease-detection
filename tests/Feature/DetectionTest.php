<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Http;
use PHPUnit\Framework\Attributes\DataProvider;
use Tests\TestCase;

class DetectionTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        $this->actingAs(User::factory()->create());
    }

    private function leaf()
    {
        return UploadedFile::fake()->createWithContent('leaf.png', base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='));
    }

    public static function enabledCrops(): iterable
    {
        $catalogue = json_decode(file_get_contents(dirname(__DIR__, 2).'/ai-service/crops.json'), true, flags: JSON_THROW_ON_ERROR);
        foreach ($catalogue as $key => $spec) {
            yield $key => [$key, $spec];
        }
    }

    #[DataProvider('enabledCrops')]
    public function test_enabled_crop_reaches_ai_and_uses_its_exact_catalogue(string $crop, array $spec): void
    {
        $label = $spec['classes'][0];
        $match = ['label' => $label, 'display_label' => $spec['label'].' - Example match', 'crop' => $spec['label'], 'disease' => 'Example match', 'confidence' => .9];
        Http::fake(['*/predict' => Http::response([...$match, 'selected_crop' => $crop, 'uncertain' => false, 'top_predictions' => [$match]])]);
        $this->from('/portal')->post('/detect', ['crop' => $crop, 'image' => $this->leaf()])
            ->assertSessionHas('prediction.label', $label)
            ->assertSessionHas('prediction.limited_coverage', $spec['coverage'] !== 'healthy_and_diseases');
        $page = $this->get('/portal')->assertOk();
        if ($spec['coverage'] !== 'healthy_and_diseases') {
            $page->assertSee('Limited model coverage')->assertSee($spec['note']);
        }
        Http::assertSentCount(1);
    }

    public function test_unlisted_class_inside_an_enabled_crop_is_rejected(): void
    {
        $match = ['label' => 'Potato___Invented_disease', 'display_label' => 'Invalid', 'crop' => 'Potato', 'disease' => 'Invalid', 'confidence' => .9];
        Http::fake(['*/predict' => Http::response([...$match, 'selected_crop' => 'potato', 'uncertain' => false, 'top_predictions' => [$match]])]);
        $this->from('/portal')->post('/detect', ['crop' => 'potato', 'image' => $this->leaf()])->assertSessionHasErrors('image')->assertSessionMissing('prediction');
    }

    public function test_valid_prediction_is_displayed(): void
    {
        $match = ['label' => 'Tomato___Early_blight', 'display_label' => 'Tomato - Early blight',
            'crop' => 'Tomato', 'disease' => 'Early blight', 'confidence' => .85];
        Http::fake(['*/predict' => Http::response([...$match, 'uncertain' => false, 'selected_crop' => 'tomato',
            'top_predictions' => [$match, [...$match, 'confidence' => .10], [...$match, 'confidence' => .05]]])]);
        $this->from('/portal')->post('/detect', ['crop' => 'tomato', 'image' => $this->leaf()])->assertRedirect('/portal')->assertSessionHas('prediction');
        $this->get('/portal')->assertSee('Early blight')->assertSee('85.0');
        Http::assertSent(fn ($request) => str_ends_with($request->url(), '/predict') && $request->hasFile('file') && collect($request->data())->contains(fn ($part) => $part['name'] === 'crop' && $part['contents'] === 'tomato'));
    }

    public function test_model_failure_is_not_reported_as_untrained(): void
    {
        Http::fake(['*/predict' => Http::response(['detail' => 'Unavailable'], 503)]);
        $this->from('/portal')->post('/detect', ['crop' => 'tomato', 'image' => $this->leaf()])->assertSessionHasErrors('image');
        $this->get('/portal')->assertSee('still initializing or could not load')->assertDontSee('not trained');
    }

    public function test_malformed_result_is_rejected(): void
    {
        Http::fake(['*/predict' => Http::response(['label' => 'invalid'])]);
        $this->from('/portal')->post('/detect', ['crop' => 'tomato', 'image' => $this->leaf()])->assertSessionHasErrors('image')->assertSessionMissing('prediction');
    }

    public function test_health_reports_loading(): void
    {
        Http::fake(['*/health' => Http::response(['status' => 'loading'])]);
        $this->getJson('/detect/health')->assertOk()->assertJson(['status' => 'loading']);
    }

    public function test_invalid_upload_never_reaches_ai(): void
    {
        Http::fake();
        $this->post('/detect', ['crop' => 'tomato', 'image' => UploadedFile::fake()->create('document.txt')])->assertSessionHasErrors('image');
        Http::assertNothingSent();
    }

    public function test_crop_is_required_and_cassava_is_unavailable(): void
    {
        Http::fake();
        foreach ([null, 'rice', 'cassava'] as $crop) {
            $this->from('/portal')->post('/detect', ['crop' => $crop, 'image' => $this->leaf()])->assertSessionHasErrors('crop');
        }
        Http::assertNothingSent();
    }

    public function test_pepper_accepts_only_two_supported_matches(): void
    {
        $match = ['label' => 'Pepper,_bell___healthy', 'display_label' => 'Pepper, bell - Healthy',
            'crop' => 'Pepper, bell', 'disease' => 'Healthy', 'confidence' => .8];
        Http::fake(['*/predict' => Http::response([...$match, 'uncertain' => false, 'selected_crop' => 'pepper',
            'top_predictions' => [$match, [...$match, 'label' => 'Pepper,_bell___Bacterial_spot', 'confidence' => .1]]])]);
        $this->from('/portal')->post('/detect', ['crop' => 'pepper', 'image' => $this->leaf()])->assertSessionHas('prediction');
        $this->get('/portal')->assertSee('Top 2 possible matches')->assertSee('value="pepper" selected', false);
    }

    public function test_predictions_for_another_crop_are_rejected(): void
    {
        $match = ['label' => 'Potato___Early_blight', 'display_label' => 'Potato - Early blight',
            'crop' => 'Potato', 'disease' => 'Early blight', 'confidence' => .85];
        Http::fake(['*/predict' => Http::response([...$match, 'uncertain' => false, 'selected_crop' => 'tomato',
            'top_predictions' => [$match]])]);
        $this->from('/portal')->post('/detect', ['crop' => 'tomato', 'image' => $this->leaf()])->assertSessionHasErrors('image')->assertSessionMissing('prediction');
    }

    public function test_weak_crop_match_is_presented_as_unconfirmed(): void
    {
        $match = ['label' => 'Tomato___Early_blight', 'display_label' => 'Tomato - Early blight',
            'crop' => 'Tomato', 'disease' => 'Early blight', 'confidence' => .00086958];
        Http::fake(['*/predict' => Http::response([...$match, 'uncertain' => true, 'selected_crop' => 'tomato',
            'uncertainty_reason' => 'crop_conflict', 'top_predictions' => [$match]])]);
        $this->from('/portal')->post('/detect', ['crop' => 'tomato', 'image' => $this->leaf()])->assertSessionHas('prediction');
        $this->get('/portal')->assertSee('Unable to identify confidently')->assertSee('0.09')
            ->assertSee('tentative matches, not a diagnosis')->assertSee('outside your selected crop')
            ->assertDontSee('Pepper has two supported classes.');
    }
}
